"""Several people signed in on one device, switching between them, and staying signed in.

It works the way switching Google accounts does. Each account signed in on this
browser keeps its own session, and a signed cookie lists them. Switching hands
the browser back one of those sessions, so nobody retypes a password while they
are still signed in.

Signed in means until the device goes unused for SESSION_COOKIE_AGE (48 hours).
While anyone uses the app on it, every account signed in there is kept signed
in: the device is in use, so none of them has been left idle. Once the device
has sat unused that long, the sessions end. The accounts stay listed, and the
first switch to one asks for that person's password again, their name filled in.
"Sign out" takes an account off the list; changing a password ends it too.

The cookie holds session keys, so it is exactly as private as the session
cookie itself: HttpOnly, and Secure wherever the session cookie is. It is signed
so its contents cannot be edited, and it lists only sessions that were opened
in this browser.
"""

import time

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.core import signing
from django.middleware.csrf import rotate_token
from django.utils.crypto import constant_time_compare
from django.utils.module_loading import import_string

COOKIE = "tw_accounts"
SALT = "titans.accounts-on-device"
MOST = 5  # accounts one device keeps signed in at once
# The list itself outlives the sessions in it, so an account that timed out is
# still one tap (and a password) away rather than gone.
REMEMBER_FOR = 365 * 24 * 3600
# The session records the hour it was last used in, so the 48 hours restart at
# most once an hour — one small write, not one on every page.
ACTIVE_HOUR = "_active_hour"


def _store_class():
    return import_string(f"{settings.SESSION_ENGINE}.SessionStore")


def entries(request):
    """What this browser's cookie lists: [{"k": session key, "u": user id, "n": name, "r": role}], newest first."""
    raw = request.COOKIES.get(COOKIE)
    if not raw:
        return []
    try:
        found = signing.loads(raw, salt=SALT, max_age=REMEMBER_FOR)
    except signing.BadSignature:
        return []
    return [entry for entry in found if isinstance(entry, dict) and {"k", "u", "n", "r"} <= entry.keys()]


def others(request):
    """The other accounts listed on this device, for the menu. Read from the cookie alone — no database."""
    me = request.user.pk if request.user.is_authenticated else None
    return [entry for entry in entries(request) if entry["u"] != me]


def write(response, listed):
    if not listed:
        response.delete_cookie(COOKIE, samesite="Lax")
        return
    response.set_cookie(
        COOKIE,
        signing.dumps(listed[:MOST], salt=SALT, compress=True),
        max_age=REMEMBER_FOR,
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="Lax",
    )


def live_session(entry):
    """The entry's session if it is still signed in as that person, else None.

    It has to exist, belong to that user, who is still active, and have been made
    with their current password — changing a password signs out everywhere else.
    """
    from .models import User

    store = _store_class()(session_key=entry["k"])
    data = store.load()
    if not data or str(data.get(SESSION_KEY)) != str(entry["u"]):
        return None
    user = User.objects.filter(pk=entry["u"], is_active=True).first()
    if user is None or not constant_time_compare(data.get(HASH_SESSION_KEY, ""), user.get_session_auth_hash()):
        return None
    if data.get(BACKEND_SESSION_KEY) not in settings.AUTHENTICATION_BACKENDS:
        return None
    return store


def accounts_here(request):
    """Every account listed on this device, with its user and whether it is still signed in. Checks the database."""
    from .models import User

    listed = entries(request)
    people = User.objects.filter(is_active=True).in_bulk([entry["u"] for entry in listed])
    return [
        {**entry, "user": people[entry["u"]], "live": live_session(entry) is not None}
        for entry in listed
        if entry["u"] in people
    ]


def _keep_alive(key):
    """Restart another account's 48 hours, if it is still signed in."""
    store = _store_class()(session_key=key)
    if store.get(SESSION_KEY):
        store.save()


def switch_to(request, user_id):
    """Make this browser use the other account's session. Returns that user, or None if it has ended."""
    entry = next((item for item in entries(request) if item["u"] == user_id), None)
    store = live_session(entry) if entry else None
    if store is None:
        return None
    request.session = store
    # Saved and sent as the session cookie by SessionMiddleware on the way out.
    request.session.modified = True
    rotate_token(request)
    from .models import User

    return User.objects.get(pk=user_id)


def detach(request):
    """Start a fresh, empty session so signing in someone else leaves the current one signed in."""
    request.session = _store_class()()


def forget_all(request):
    """Sign out of every account on this device — and stop its notifications for each of them."""
    from apps.crm import push

    for entry in entries(request):
        store = _store_class()(session_key=entry["k"])
        data = store.load()
        push.forget_device(data.get(SESSION_KEY), data.get(push.SESSION_KEY))
        store.delete()


class RememberAccounts:
    """Keeps this device's accounts listed, and signed in while the device is in use.

    The account signed in is added to the device's list. A second sign-in by the
    same person replaces their older one, and that older session is ended — it
    could otherwise never be reached again.

    Once an hour of use, the 48 hours restart for the account in use and for
    every other account still signed in here.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "user", None)
        session = getattr(request, "session", None)
        if not (user and user.is_authenticated and session is not None and session.session_key):
            return response

        listed = entries(request)
        key = session.session_key
        if not any(entry["k"] == key for entry in listed):
            listed = self._add(listed, key, user)
            write(response, listed)

        hour = int(time.time() // 3600)
        if session.get(ACTIVE_HOUR) != hour:
            # Saved by SessionMiddleware on the way out, which pushes its end 48 hours on.
            session[ACTIVE_HOUR] = hour
            for entry in listed:
                if entry["k"] != key:
                    _keep_alive(entry["k"])
        return response

    @staticmethod
    def _add(listed, key, user):
        listed = [{"k": key, "u": user.pk, "n": user.display_name, "r": user.get_role_display()}, *listed]
        kept, dropped = [], []
        for entry in listed:
            # Their older session here, or one pushed off the end of the list.
            superseded = entry["u"] == user.pk and entry["k"] != key
            (dropped if superseded or len(kept) >= MOST else kept).append(entry)
        for entry in dropped:
            _store_class()(session_key=entry["k"]).delete()
        return kept
