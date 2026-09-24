"""Staff records, and the password every new account has to set for itself."""

from functools import wraps

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import DEFAULT_PASSWORD, EmployeeForm, FirstPasswordForm
from .models import Role, User


def super_admin_only(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_super_admin:
            return HttpResponseForbidden("Only the Super Admin can manage employees.")
        return view(request, *args, **kwargs)

    return wrapper


@super_admin_only
def employee_list(request):
    form = EmployeeForm()
    if request.method == "POST":
        form = EmployeeForm(request.POST)
        if form.is_valid():
            employee = form.save()
            messages.success(
                request,
                f"{employee.display_name} added as {employee.get_role_display()}. "
                f"They sign in as {employee.username} with the password {DEFAULT_PASSWORD}, "
                "and will be asked to change it.",
            )
            return redirect("accounts:employee_list")

    # Grouped the way the team is actually organised.
    groups = []
    for value, label in Role.choices:
        people = User.objects.filter(role=value, is_active=True)
        if people:
            groups.append({"role": label, "people": people})

    return render(
        request,
        "accounts/employee_list.html",
        {
            "groups": groups,
            "form": form,
            "default_password": DEFAULT_PASSWORD,
            "total": User.objects.filter(is_active=True).count(),
        },
    )


@super_admin_only
@require_POST
def employee_reset(request, pk):
    """Put someone back on the default password — for a forgotten one."""
    employee = get_object_or_404(User, pk=pk, is_active=True)
    employee.set_password(DEFAULT_PASSWORD)
    employee.must_change_password = True
    employee.save(update_fields=["password", "must_change_password"])
    messages.success(
        request,
        f"{employee.display_name} is back on {DEFAULT_PASSWORD} and will be asked to change it.",
    )
    return redirect("accounts:employee_list")


@super_admin_only
@require_POST
def employee_remove(request, pk):
    """Switched off rather than deleted, so their finished work keeps its name."""
    employee = get_object_or_404(User, pk=pk, is_active=True)
    if employee.pk == request.user.pk:
        messages.error(request, "You cannot remove your own account.")
        return redirect("accounts:employee_list")
    employee.is_active = False
    employee.save(update_fields=["is_active"])
    messages.success(request, f"{employee.display_name} can no longer sign in.")
    return redirect("accounts:employee_list")


@login_required
def change_password(request):
    """Both the forced first change and any later one the person wants."""
    forced = request.user.must_change_password
    form = FirstPasswordForm(request.user)
    if request.method == "POST":
        form = FirstPasswordForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            # Changing the password would otherwise sign them straight out.
            update_session_auth_hash(request, request.user)
            if forced:
                request.user.must_change_password = False
                request.user.save(update_fields=["must_change_password"])
            messages.success(request, "Password changed.")
            return redirect("crm:dashboard")

    return render(
        request,
        "accounts/change_password.html",
        {
            "form": form,
            "forced": forced,
            "default_password": DEFAULT_PASSWORD,
            # No sidebar on the forced screen — there is nowhere to go yet.
            "hide_chrome": forced,
        },
    )
