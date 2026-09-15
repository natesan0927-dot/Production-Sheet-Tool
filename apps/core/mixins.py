from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from apps.core.exports import is_registered


class AutoLocalExportMixin:
    """
    Attach to any CreateView/UpdateView whose model is registered in
    apps.core.exports. After a successful save it appends ?autoexport=1 to the
    redirect URL; base.html then auto-triggers a same-tab download of a
    PDF/Excel copy of the record straight to the employee's own machine, and
    the server keeps a timestamped backup copy under DOCUMENT_BACKUP_ROOT.
    """

    def get_success_url(self):
        url = super().get_success_url()
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}autoexport=1"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = getattr(self, "object", None)
        if obj is not None:
            content_type = ContentType.objects.get_for_model(type(obj))
            if is_registered(content_type.model):
                ctx["local_copy_url"] = reverse(
                    "core:local_copy", args=[content_type.app_label, content_type.model, obj.pk]
                )
                if self.request.GET.get("autoexport") == "1":
                    ctx["autoexport_url"] = ctx["local_copy_url"]
        return ctx


class RoleRequiredMixin:
    """
    Restrict a class-based view to members of specific Django groups (roles).

    Prefer `section = "production"` (looked up against
    apps.core.access.SECTION_ROLES, the same table that drives the sidebar) so
    a role always sees exactly the pages its sidebar links point at. Pass
    `allowed_groups` directly only for a one-off restriction that doesn't map
    to a whole nav section.
    """

    allowed_groups = ()
    section = None

    def get_allowed_groups(self):
        if self.section:
            from apps.core.access import SECTION_ROLES

            return SECTION_ROLES.get(self.section, ())
        return self.allowed_groups

    def dispatch(self, request, *args, **kwargs):
        from django.contrib.auth.mixins import LoginRequiredMixin  # local import to avoid cycle at import time

        if not request.user.is_authenticated:
            return LoginRequiredMixin().handle_no_permission()
        if request.user.is_superuser or request.user.is_staff:
            return super().dispatch(request, *args, **kwargs)
        allowed_groups = self.get_allowed_groups()
        if not allowed_groups:
            return super().dispatch(request, *args, **kwargs)
        if request.user.groups.filter(name__in=list(allowed_groups) + ["Super Admin"]).exists():
            return super().dispatch(request, *args, **kwargs)
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied("You do not have access to this section.")


def require_role(*roles):
    """
    Function-view decorator for an approval-style action that must be done by
    someone other than whoever did the preceding step (e.g. a Measurement
    Staff member should not be able to approve their own final measurement).
    Unlike require_section, this checks an explicit, narrow role list rather
    than a whole nav section.
    """

    def decorator(view_func):
        from functools import wraps

        from django.contrib.auth.decorators import login_required
        from django.core.exceptions import PermissionDenied

        @login_required
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if request.user.is_superuser or request.user.is_staff or request.user.has_role(*roles, "Super Admin"):
                return view_func(request, *args, **kwargs)
            raise PermissionDenied("This action requires approval by an authorized role.")

        return wrapped

    return decorator


def require_section(section):
    """Function-view equivalent of RoleRequiredMixin(section=...)."""

    def decorator(view_func):
        from functools import wraps

        from django.contrib.auth.decorators import login_required
        from django.core.exceptions import PermissionDenied

        from apps.core.access import SECTION_ROLES

        @login_required
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if request.user.is_superuser or request.user.is_staff:
                return view_func(request, *args, **kwargs)
            allowed = SECTION_ROLES.get(section, ())
            if request.user.groups.filter(name__in=list(allowed) + ["Super Admin"]).exists():
                return view_func(request, *args, **kwargs)
            raise PermissionDenied("You do not have access to this section.")

        return wrapped

    return decorator
