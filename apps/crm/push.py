"""Notifications on the phone: the banner, even when the app is closed.

Every update the app sends someone (updates.send) is also pushed to each device
where that person turned notifications on: the phone shows it like any other
app's notification, and tapping it opens the page it is about.

This is the Web Push standard. When notifications are turned on, the browser
gives a subscription: an address at its own push service (Google's for Chrome
and Android, Apple's for iPhone, Mozilla's, Microsoft's) and two keys. Each
message is encrypted for that one device, so the push service cannot read it
(RFC 8291), and signed with this site's key, so the push service knows who is
sending (VAPID, RFC 8292).

The site's key is worked out from SECRET_KEY, so there is nothing to set up. If
SECRET_KEY is ever changed, every device quietly subscribes again the next time
the app is opened.

Pushes go out on a background thread once the database has saved the update,
so no page ever waits on Google or Apple.
"""

import base64
import functools
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from urllib.parse import urlsplit

import http_ece
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import connection, transaction
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from py_vapid import Vapid02

logger = logging.getLogger(__name__)

TITLE = "Titans Windows"
# Only real push services are ever sent to, so a subscription cannot be used to
# make this server post to an address of someone's choosing.
PUSH_SERVICES = (".googleapis.com", ".push.apple.com", ".push.services.mozilla.com", ".notify.windows.com")
# How long a push service keeps trying a phone that is switched off.
KEEP_FOR = 24 * 3600
P256_ORDER = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@functools.lru_cache(maxsize=4)
def _site_key(secret):
    seed = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"titans-web-push", info=b"vapid p-256").derive(secret.encode())
    return ec.derive_private_key(int.from_bytes(seed, "big") % (P256_ORDER - 1) + 1, ec.SECP256R1())


def site_key():
    return _site_key(settings.SECRET_KEY)


def public_key():
    """This site's key as the browser wants it when subscribing."""
    point = site_key().public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return _b64(point)


def acceptable(endpoint):
    """Whether a subscription's address is a real push service (or a test stand-in named in settings)."""
    parts = urlsplit(endpoint or "")
    if parts.scheme == "https" and parts.hostname and any(f".{parts.hostname}".endswith(s) for s in PUSH_SERVICES):
        return True
    return any(endpoint.startswith(prefix) for prefix in settings.WEBPUSH_TEST_ENDPOINTS if prefix)


def valid_keys(p256dh, auth):
    try:
        return len(_unb64(p256dh)) == 65 and len(_unb64(auth)) == 16
    except (ValueError, TypeError):
        return False


def send(subscription, payload):
    """Push one message to one device. Returns the push service's HTTP status (0 if unreachable)."""
    body = http_ece.encrypt(
        json.dumps(payload).encode(),
        salt=os.urandom(16),
        private_key=ec.generate_private_key(ec.SECP256R1()),
        dh=_unb64(subscription.p256dh),
        auth_secret=_unb64(subscription.auth),
        version="aes128gcm",
    )
    parts = urlsplit(subscription.endpoint)
    headers = Vapid02(private_key=site_key()).sign(
        {"aud": f"{parts.scheme}://{parts.netloc}", "exp": int(time.time()) + 12 * 3600, "sub": settings.WEBPUSH_SUBJECT}
    )
    headers.update({
        "TTL": str(KEEP_FOR),
        "Urgency": "high",
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
    })
    request = urllib.request.Request(subscription.endpoint, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status
    except urllib.error.HTTPError as refused:
        return refused.code
    except (urllib.error.URLError, OSError):
        return 0


def payload_for(note):
    return {
        "title": TITLE,
        "body": note.message,
        "url": note.url or reverse("crm:notifications"),
        "tag": f"titans-{note.pk}" if note.pk else "titans",
    }


def deliver(notes):
    """Push these new notifications to their people's devices, once they are saved."""
    items = [(note.user_id, payload_for(note)) for note in notes]
    if not items:
        return
    transaction.on_commit(lambda: _start(items))


def _start(items):
    from .models import PushSubscription

    # Most updates go to people with no device registered: nothing to start a thread for.
    if not PushSubscription.objects.filter(user_id__in={user for user, _ in items}).exists():
        return
    if settings.WEBPUSH_INLINE:
        _send_all(items)
    else:
        # Not a daemon: a server worker being recycled waits for pushes already on their way.
        threading.Thread(target=_send_all, args=(items,), name="web-push").start()


def _send_all(items):
    from .models import PushSubscription

    try:
        devices = list(PushSubscription.objects.filter(user_id__in={user for user, _ in items}).select_related("user"))
        # A phone shared by two people who both turned notifications on: say whose it is.
        people_per_device = Counter(
            PushSubscription.objects.filter(endpoint__in={d.endpoint for d in devices}).values_list("endpoint", flat=True)
        )
        shared = {endpoint for endpoint, count in people_per_device.items() if count > 1}
        for user_id, payload in items:
            for device in (d for d in devices if d.user_id == user_id):
                message = dict(payload)
                if device.endpoint in shared:
                    message["title"] = f"{TITLE} · {device.user.display_name}"
                status = send(device, message)
                if status in (404, 410):
                    # The phone unsubscribed, or the app was removed: stop sending there.
                    device.delete()
                elif 200 <= status < 300:
                    PushSubscription.objects.filter(pk=device.pk).update(last_sent_at=timezone.now())
                else:
                    logger.warning("Push to %s for user %s failed with %s", urlsplit(device.endpoint).hostname, user_id, status)
    except Exception:
        logger.exception("Sending push notifications failed")
    finally:
        # The thread's own database connection, which nothing else will close.
        if not settings.WEBPUSH_INLINE:
            connection.close()


def context(request):
    """The site's push key, and the device already registered for this person in this session.

    The script compares the two with the browser's own subscription and only
    tells the server when something has changed: a newly switched-to account,
    a fresh sign-in, or a push service that handed out a new address.
    """
    from .models import PushSubscription

    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return {}
    endpoint = request.session.get(SESSION_KEY, "")
    if endpoint and not PushSubscription.objects.filter(user=user, endpoint=endpoint).exists():
        endpoint = ""
    return {"push_public_key": public_key(), "push_endpoint": endpoint}


# ---------------------------------------------------------------- the device turning them on and off
SESSION_KEY = "push_endpoint"


def _device(request):
    """A short name for the device, from its browser: "Android · Chrome"."""
    agent = request.META.get("HTTP_USER_AGENT", "")
    system = next((name for key, name in (("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"),
                                           ("Windows", "Windows"), ("Mac OS", "Mac"), ("Linux", "Linux")) if key in agent), "")
    browser = next((name for key, name in (("Edg/", "Edge"), ("SamsungBrowser", "Samsung Internet"), ("Firefox", "Firefox"),
                                            ("Chrome", "Chrome"), ("Safari", "Safari")) if key in agent), "")
    return " · ".join(part for part in (system, browser) if part)[:200]


def _read(request):
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


@login_required
@require_POST
def subscribe(request):
    """This device wants the signed-in person's notifications."""
    from .models import PushSubscription

    data = _read(request)
    endpoint = str(data.get("endpoint") or "")
    keys = data.get("keys") if isinstance(data.get("keys"), dict) else {}
    p256dh, auth = str(keys.get("p256dh") or ""), str(keys.get("auth") or "")
    if len(endpoint) > 1000 or not acceptable(endpoint) or not valid_keys(p256dh, auth):
        return JsonResponse({"ok": False, "error": "That is not a notification subscription this app can use."}, status=400)
    PushSubscription.objects.update_or_create(
        user=request.user, endpoint=endpoint, defaults={"p256dh": p256dh, "auth": auth, "device": _device(request)}
    )
    request.session[SESSION_KEY] = endpoint
    return JsonResponse({"ok": True})


@login_required
@require_POST
def unsubscribe(request):
    """No more notifications for the signed-in person on this device. Others on it keep theirs."""
    from .models import PushSubscription

    endpoint = str(_read(request).get("endpoint") or request.session.get(SESSION_KEY) or "")
    removed, _ = PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
    request.session.pop(SESSION_KEY, None)
    return JsonResponse({"ok": True, "removed": removed})


@login_required
@require_POST
def test(request):
    """Send a test notification to this device, and say whether the push service took it."""
    from .models import PushSubscription

    device = PushSubscription.objects.filter(user=request.user, endpoint=request.session.get(SESSION_KEY, "")).first()
    if device is None:
        return JsonResponse({"ok": False, "error": "Notifications are not on for you on this device yet."}, status=400)
    status = send(device, {"title": TITLE, "body": "Notifications are working on this device.",
                           "url": reverse("crm:notifications"), "tag": "titans-test"})
    if status in (404, 410):
        device.delete()
    if 200 <= status < 300:
        return JsonResponse({"ok": True})
    return JsonResponse({"ok": False, "error": f"The notification service did not accept it ({status or 'unreachable'})."}, status=502)


def forget_device(user_id, endpoint):
    """Someone signed out on a device: it stops getting their notifications."""
    from .models import PushSubscription

    if user_id and endpoint:
        PushSubscription.objects.filter(user_id=user_id, endpoint=endpoint).delete()
