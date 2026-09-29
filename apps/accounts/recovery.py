"""Forgotten passwords.

Two people, two routes, because they have different people to turn to.

**Everyone but the Super Admin** raises a request from the sign-in page. It shows
up for the Super Admin in three places — a notification, the dashboard, and the
Employees page — and they set that person a new password and tell them. The
person then signs in with it and is made to choose their own straight away, so
the password the Super Admin typed is only ever a stepping stone. No code, no
email, nothing to relay: the Super Admin is the one who acts, so the check that it
really is the right person is theirs to make, by phone or across the desk.

**The Super Admin** has no one above them, so an OTP is texted to the mobile
number they registered in their profile, and entered on the reset page with the
new password. The number is proved when it is registered (see start_phone_check).
If a reset OTP cannot be texted it goes to the server log, so a failed text can
never lock the only administrator out.

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


def _asked_too_often(user, purpose):
    hour_ago = timezone.now() - timedelta(hours=1)
    return user.reset_codes.filter(purpose=purpose, created_at__gte=hour_ago).count() >= PasswordResetCode.MAX_PER_HOUR


def _issue(user, purpose, phone=""):
    """A fresh OTP of this kind. Only the newest works; asking again retires the last one."""
    code = _new_code()
    with transaction.atomic():
        user.reset_codes.filter(purpose=purpose, used_at__isnull=True).update(used_at=timezone.now())
        PasswordResetCode.objects.create(
            user=user,
            purpose=purpose,
            phone=phone,
            code_hash=make_password(code),
            expires_at=timezone.now() + PasswordResetCode.LIFETIME,
        )
    return code


def request_code(user):
    """Text the Super Admin a password-reset OTP. False if they have asked too often lately."""
    if _asked_too_often(user, PasswordResetCode.Purpose.RESET):
        return False
    sms.send_admin_code(user, _issue(user, PasswordResetCode.Purpose.RESET))
    return True


def start_phone_check(user, number):
    """Text an OTP to a new mobile number to prove it. Returns (sent, why not)."""
    number = sms.mobile_digits(number)
    if not number:
        return False, "That is not a 10-digit mobile number."
    if _asked_too_often(user, PasswordResetCode.Purpose.VERIFY):
        return False, "Three OTPs have been sent in the last hour. Wait a while, then try again."
    code = _issue(user, PasswordResetCode.Purpose.VERIFY, phone=number)
    sent, reason = sms.send_otp(number, code)
    if not sent:
        # Never delivered, so it can never be typed back.
        user.reset_codes.filter(purpose=PasswordResetCode.Purpose.VERIFY, used_at__isnull=True).update(used_at=timezone.now())
    return sent, reason


def pending_phone(user):
    """The number an OTP was last sent to for proving, while that OTP is still usable."""
    live = user.reset_codes.filter(purpose=PasswordResetCode.Purpose.VERIFY, used_at__isnull=True).order_by("-created_at").first()
    return live.phone if live and live.is_usable else ""


def finish_phone_check(user, typed_code):
    """The OTP typed back: right, and the number is registered and proved. Returns True if so."""
    live = user.reset_codes.filter(purpose=PasswordResetCode.Purpose.VERIFY, used_at__isnull=True).order_by("-created_at").first()
    number = live.phone if live else ""
    if not number or not spend_code(user, typed_code, PasswordResetCode.Purpose.VERIFY):
        return False
    user.phone = number
    user.phone_verified_at = timezone.now()
    user.save(update_fields=["phone", "phone_verified_at"])
    return True


def spend_code(user, typed_code, purpose=PasswordResetCode.Purpose.RESET):
    """Check a typed OTP. True (and it is used up) if it is the live one of this kind.

    A wrong guess counts against the live OTP, which gives up after five, so the
    million possible codes cannot be walked through.
    """
    live = user.reset_codes.filter(purpose=purpose, used_at__isnull=True).order_by("-created_at").first()
    if live is None or not live.is_usable:
        return False

    if not check_password((typed_code or "").strip(), live.code_hash):
        live.tries += 1
        live.save(update_fields=["tries"])
        return False

    live.used_at = timezone.now()
    live.save(update_fields=["used_at"])
    return True
