"""Texting a one-time password (OTP) to the Super Admin's mobile.

The Super Admin has no one above them to reset a forgotten password, so it is
done by an OTP texted to the mobile number they register in their own profile.
The number is proved when it is set — an OTP goes to it and has to be typed back
— so a mistyped number is caught then, not on the day it is needed.

Texts go through Fast2SMS's Quick SMS route: about ₹5 a text, from a random
numeric sender, and no DLT registration or website verification. Its OTP route
is cheaper but refuses to send until the account passes a website check, and
its Smart OTP needs a DLT-registered template; FAST2SMS_ROUTE=otp switches to
the OTP route if that check is ever done. Putting FAST2SMS_API_KEY on the host
is all it takes to switch texts on.

If a password-reset OTP cannot be texted — the SMS account has run out of
balance, say — it is written to the server log as a last resort, so a failed
text never locks the only administrator out. On Render the log is readable only
by whoever owns the hosting account, who could change the database directly
anyway, so this opens no door that was shut. Proving a new number never falls
back to the log: the whole point is that the text arrives.
"""

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

from .models import PasswordResetCode

logger = logging.getLogger(__name__)


def mobile_digits(value):
    """A ten-digit Indian mobile number from however it was typed, or ''."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if len(digits) == 10 and digits[0] in "6789" else ""


def masked(number):
    """98xxxxxx10 — enough to recognise your own number, not enough to learn someone else's."""
    number = mobile_digits(number) or number or ""
    return f"{number[:2]}{'x' * (len(number) - 4)}{number[-2:]}" if len(number) >= 6 else number


def configured():
    """Whether texts can be sent at all."""
    provider = settings.SMS_PROVIDER or ("fast2sms" if settings.FAST2SMS_API_KEY else "")
    return provider == "fast2sms" and bool(settings.FAST2SMS_API_KEY)


def _message(code):
    """One short text: a longer one is sent, and charged, as two."""
    minutes = int(PasswordResetCode.LIFETIME.total_seconds() // 60)
    return f"Your Titans Windows OTP is {code}. It works for {minutes} minutes. Do not share it with anyone."


def _fast2sms(number, code):
    if settings.FAST2SMS_ROUTE == "otp":
        fields = {"route": "otp", "variables_values": code, "numbers": number}
    else:
        fields = {"route": "q", "message": _message(code), "numbers": number}
    body = urllib.parse.urlencode(fields).encode()
    request = urllib.request.Request(
        settings.FAST2SMS_URL,
        data=body,
        headers={
            "authorization": settings.FAST2SMS_API_KEY,
            "Content-Type": "application/x-www-form-urlencoded",
            "Cache-Control": "no-cache",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            reply = json.loads(response.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as refused:
        # Fast2SMS explains a refusal in the body: a bad key, no balance, a bad number.
        try:
            reply = json.loads(refused.read().decode("utf-8", "replace") or "{}")
        except ValueError:
            reply = {}
        return False, _reason(reply) or f"the SMS service answered {refused.code}"
    if reply.get("return") is True:
        return True, ""
    return False, _reason(reply) or "the SMS service did not accept it"


def _reason(reply):
    message = reply.get("message")
    if isinstance(message, list):
        message = " ".join(str(part) for part in message)
    return str(message or "").strip()


def send_otp(number, code):
    """Text an OTP. Returns (sent, why not) — the reason is shown to the Super Admin."""
    number = mobile_digits(number)
    if not number:
        return False, "That is not a 10-digit mobile number."
    if not configured():
        return False, "Texts are not switched on for this site yet — FAST2SMS_API_KEY has to be added on the host."
    try:
        sent, reason = _fast2sms(number, code)
    except Exception:
        logger.warning("Could not reach the SMS service", exc_info=True)
        return False, "The SMS service could not be reached. Try again in a minute."
    if not sent:
        logger.warning("The SMS service did not send an OTP to %s: %s", masked(number), reason)
        return False, f"The SMS service did not send it: {reason}."
    return True, ""


def send_admin_code(user, code):
    """Text a password-reset OTP to the Super Admin. Returns "sms", or "log" if it could only be logged."""
    if user.phone:
        sent, reason = send_otp(user.phone, code)
        if sent:
            return "sms"
        logger.warning("The reset OTP for %s was not texted: %s", user.username, reason)
    else:
        logger.warning("%s has no registered mobile number to text a reset OTP to", user.username)

    # The last resort: the log, so a Super Admin is never locked out by a failed
    # text. Note that the OTP appears here and nowhere else.
    logger.warning("PASSWORD RESET CODE for %s (no SMS was sent): %s", user.username, code)
    return "log"
