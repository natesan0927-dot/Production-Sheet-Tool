"""Nobody gets past the change-password screen on a shared default password."""

from django.shortcuts import redirect
from django.urls import Resolver404, resolve

ALLOWED = {
    "accounts:change_password",
    "accounts:logout",
    "accounts:logout_everyone",
    "accounts:login",
    "accounts:switch_account",
}


def _page_name(path):
    try:
        return resolve(path).view_name
    except Resolver404:
        return ""


class ForcePasswordChange:
    """Sends anyone still on the password they were given to pick their own.

    Only the change-password page, signing out, switching to another account
    signed in on the device, and the static files stay reachable — everything
    else redirects, so a default password cannot be left in place by simply
    navigating around it.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated and user.must_change_password:
            if _page_name(request.path) not in ALLOWED and not request.path.startswith(("/static/", "/media/")):
                return redirect("accounts:change_password")
        return self.get_response(request)
