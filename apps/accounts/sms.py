"""Getting a password-reset code to the Super Admin.

Staff who forget a password are helped by the Super Admin, who is already in the
app: the code goes to their bell. The Super Admin has no one above them to ask,
so their code is texted to the mobile number registered on their account.

Sending a text needs an account with an SMS provider, which costs money and, in
India, needs some registration. Until one is set up the code is written to the
server log instead, and the reset page says nothing different either way — it
never reveals whether an account exists, or how the code travelled. On Render the
log is readable only by whoever owns the hosting account, which is the same person
who could change the database directly, so this fallback does not open a door that
was shut.

Only Fast2SMS is supported, through its OTP route, which sends a fixed
"your OTP is ..." message and so needs no template registration. That route is
written from the provider's public documentation and has not been run against the
real service; the log fallback means a mistake here cannot lock the Super Admin out.
"""

import json
import logging
import re
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)


def mobile_digits(value):
    """A ten-digit Indian mobile number from however it was typed, or ''."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if len(digits) == 10 else ""


def _fast2sms(number, code):
    body = urllib.parse.urlencode({"route": "otp", "variables_values": code, "numbers": number}).encode()
    request = urllib.request.Request(
        settings.FAST2SMS_URL,
        data=body,
        headers={
            "authorization": settings.FAST2SMS_API_KEY,
            "Content-Type": "application/x-www-form-urlencoded",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        reply = json.loads(response.read().decode("utf-8", "replace"))
    return reply.get("return") is True


def send_admin_code(user, code):
    """Text the code to the Super Admin. Returns "sms", or "log" if it could only be logged."""
    number = mobile_digits(user.phone)
    if settings.SMS_PROVIDER == "fast2sms" and settings.FAST2SMS_API_KEY and number:
        try:
            if _fast2sms(number, code):
                return "sms"
            logger.warning("The SMS provider did not accept the reset code for %s", user.username)
        except Exception:
            logger.warning("Could not reach the SMS provider for %s", user.username, exc_info=True)
    elif not number:
        logger.warning("%s has no registered mobile number to text a reset code to", user.username)

    # The last resort: the log, so a Super Admin is never locked out by a missing
    # SMS account. Note that the code appears here and nowhere else.
    logger.warning("PASSWORD RESET CODE for %s (no SMS was sent): %s", user.username, code)
    return "log"
