"""Forgotten passwords.

Two people, two routes, because they have different people to turn to.

**Everyone but the Super Admin** raises a request from the sign-in page. It shows
up for the Super Admin in three places — a notification, the dashboard, and the
Employees page — and they set that person a new password and tell them. The
person then signs in with it and is made to choose their own straight away, so
the password the Super Admin typed is only ever a stepping stone. No code, no
email, nothing to relay: the Super Admin is the one who acts, so the check that it
really is the right person is theirs to make, by phone or across the desk.

**The Super Admin** has no one above them, so their code is texted to the mobile
number registered on their account and entered on the reset page. If a text cannot
be sent the code goes to the server log, so a missing SMS account can never lock
the only administrator out.

Nothing here tells the person at the sign-in page whether the account exists, or
what happened to their request.
"""

import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from . import sms
from .models import PasswordRequest, PasswordResetCode, Role, User

CODE_DIGITS = 6
MIN_PASSWORD = 8

# Easy to say over the phone and hard to mistype. Two words, a number.
WORDS = [
    "Amber", "Anchor", "Aster", "Birch", "Blossom", "Bronze", "Canyon", "Cedar", "Clover", "Coral",
    "Crimson", "Daisy", "Ember", "Falcon", "Forest", "Garnet", "Harbor", "Indigo", "Ivory", "Jasmine",
    "Lagoon", "Lotus", "Maple", "Meadow", "Mango", "Ocean", "Olive", "Orchid", "Pearl", "Pine",
    "River", "Saffron", "Sandal", "Silver", "Sunny", "Tulip", "Velvet", "Willow", "Winter", "Zephyr",
]


def find_user(username):
    """An active account by the name typed — capitals and stray spaces ignored."""
    typed = (username or "").strip()
    if not typed:
        return None
    return User.objects.filter(username__iexact=typed, is_active=True).order_by("pk").first()


def suggest_password():
    """A temporary password the Super Admin can read out: SunnyRiver4821."""
    return f"{secrets.choice(WORDS)}{secrets.choice(WORDS)}{secrets.randbelow(9000) + 1000}"


# ---------------------------------------------------------------- everyone but the Super Admin
def open_requests():
    return PasswordRequest.objects.filter(handled_at__isnull=True, user__is_active=True).select_related("user")


def ask_for_new_password(user):
    """Raise a request, and tell the Super Admin. False if one is already waiting."""
    with transaction.atomic():
        if user.password_requests.filter(handled_at__isnull=True).exists():
            return False
        PasswordRequest.objects.create(user=user)

    from apps.crm import updates

    message = (
        f"{user.display_name} ({user.username}) has forgotten their password and is waiting "
        "for a new one. Open Employees to set it."
    )
    admins = User.objects.filter(role=Role.SUPER_ADMIN, is_active=True)
    updates.send(admins, message, topic=updates.password(user), link=updates.employees_link())
    return True


def close_requests(user, by=None):
    """Whatever the Super Admin did for this person, their request is dealt with — everywhere it showed."""
    from apps.crm import updates

    updates.clear(updates.password(user))
    return user.password_requests.filter(handled_at__isnull=True).update(handled_at=timezone.now(), handled_by=by)


# ---------------------------------------------------------------- the Super Admin
def _new_code():
    return f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"


def request_code(user):
    """Make the Super Admin a code and text it. False if they have asked too often lately."""
    hour_ago = timezone.now() - timedelta(hours=1)
    if user.reset_codes.filter(created_at__gte=hour_ago).count() >= PasswordResetCode.MAX_PER_HOUR:
        return False

    code = _new_code()
    with transaction.atomic():
        # Only the newest code works; asking again retires the last one.
        user.reset_codes.filter(used_at__isnull=True).update(used_at=timezone.now())
        PasswordResetCode.objects.create(
            user=user,
            code_hash=make_password(code),
            expires_at=timezone.now() + PasswordResetCode.LIFETIME,
        )
    sms.send_admin_code(user, code)
    return True


def spend_code(user, typed_code):
    """Check a typed code. True (and the code is used up) if it is the live one.

    A wrong guess counts against the live code, which gives up after five, so the
    million possible codes cannot be walked through.
    """
    live = user.reset_codes.filter(used_at__isnull=True).order_by("-created_at").first()
    if live is None or not live.is_usable:
        return False

    if not check_password((typed_code or "").strip(), live.code_hash):
        live.tries += 1
        live.save(update_fields=["tries"])
        return False

    live.used_at = timezone.now()
    live.save(update_fields=["used_at"])
    return True
