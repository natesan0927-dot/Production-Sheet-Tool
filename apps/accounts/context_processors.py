from . import switching


def accounts_on_device(request):
    """The other accounts signed in on this browser, for "Switch account" in the menu under your name."""
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return {}
    return {"other_accounts": switching.others(request)}
