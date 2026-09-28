"""Forgotten passwords: asking for a code, and using one.

A member of staff who forgets their password asks for a code, which appears in
the Super Admin's bell. The Super Admin gives it to them once they are sure it is
really them — a phone call, or standing next to them. That human check is the
point: no one can reset another person's account from the login page alone.

The Super Admin's own code is texted to their registered mobile number instead.

Nothing here tells the person at the login page whether the account exists, who
got the code, or how it travelled.
"""

import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from . import sms
from .models import PasswordResetCode, Role, User

CODE_DIGITS = 6


def find_user(username):
    """An active account by the name typed — capitals and stray spaces ignored."""
    typed = (username or "").strip()
    if not typed:
        return None
    return User.objects.filter(username__iexact=typed, is_active=True).order_by("pk").first()


def _new_code():
    return f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"


def request_code(user):
    """Make a code for this person and send it where it belongs.

    Returns True if one was made, False if they have asked too often lately.
    """
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

    if user.role == Role.SUPER_ADMIN:
        sms.send_admin_code(user, code)
    else:
        _tell_super_admins(user, code)
    return True


def _tell_super_admins(user, code):
    from apps.crm.models import Notification

    minutes = int(PasswordResetCode.LIFETIME.total_seconds() // 60)
    message = (
        f"Password reset code for {user.display_name} ({user.username}): {code}. "
        f"Valid for {minutes} minutes. Give it to them only once you are sure it is really them."
    )
    admins = User.objects.filter(role=Role.SUPER_ADMIN, is_active=True)
    Notification.objects.bulk_create([Notification(user=admin, message=message[:255]) for admin in admins])


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
