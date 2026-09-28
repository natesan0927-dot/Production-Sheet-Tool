"""Staff records, and the password every new account has to set for itself."""

from functools import wraps

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import recovery, sms
from .forms import DEFAULT_PASSWORD, EmployeeForm, FirstPasswordForm, ForgotPasswordForm, ResetWithCodeForm
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

    waiting = [{"request": item, "suggested": recovery.suggest_password()} for item in recovery.open_requests()]
    return render(
        request,
        "accounts/employee_list.html",
        {
            "groups": groups,
            "form": form,
            "default_password": DEFAULT_PASSWORD,
            "total": User.objects.filter(is_active=True).count(),
            "waiting": waiting,
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
    recovery.close_requests(employee, by=request.user)
    messages.success(
        request,
        f"{employee.display_name} is back on {DEFAULT_PASSWORD} and will be asked to change it.",
    )
    return redirect("accounts:employee_list")


@super_admin_only
@require_POST
def employee_set_password(request, pk):
    """Set someone a new password after they asked, and tell the Super Admin what it is.

    It is only a stepping stone: they are made to choose their own the moment
    they sign in with it, so nothing the Super Admin types stays in use.
    """
    employee = get_object_or_404(User, pk=pk, is_active=True)
    password = request.POST.get("password", "").strip()
    if len(password) < recovery.MIN_PASSWORD:
        messages.error(request, f"A temporary password needs at least {recovery.MIN_PASSWORD} characters.")
        return redirect("accounts:employee_list")

    employee.set_password(password)
    employee.must_change_password = True
    employee.save(update_fields=["password", "must_change_password"])
    recovery.close_requests(employee, by=request.user)
    messages.success(
        request,
        f"{employee.display_name} can now sign in as {employee.username} with the password {password}. "
        "Tell them; they will be asked to choose their own straight away.",
    )
    return redirect("accounts:employee_list")


@super_admin_only
@require_POST
def employee_dismiss_request(request, pk):
    """Close a request without changing anything — they remembered, or asked by mistake."""
    employee = get_object_or_404(User, pk=pk)
    recovery.close_requests(employee, by=request.user)
    messages.success(request, f"{employee.display_name}'s request is closed. Their password was not changed.")
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
    recovery.close_requests(employee, by=request.user)
    messages.success(request, f"{employee.display_name} can no longer sign in.")
    return redirect("accounts:employee_list")


@login_required
def change_password(request):
    """Both the forced first change and any later one the person wants."""
    forced = request.user.must_change_password
    form = FirstPasswordForm(request.user, forced=forced)
    if request.method == "POST":
        form = FirstPasswordForm(request.user, request.POST, forced=forced)
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


def forgot_password(request):
    """Ask for help getting back in. What comes back is the same whoever, or whatever, was typed."""
    if request.user.is_authenticated:
        return redirect("accounts:change_password")

    form = ForgotPasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        typed = form.cleaned_data["username"].strip()
        user = recovery.find_user(typed)
        if user and user.role == Role.SUPER_ADMIN:
            recovery.request_code(user)          # texted to their registered number
        elif user:
            recovery.ask_for_new_password(user)  # waits for the Super Admin, in three places
        request.session["reset_username"] = typed
        return redirect("accounts:forgot_sent")
    return render(request, "accounts/forgot_password.html", {"form": form})


def forgot_sent(request):
    """The same page for everyone: it cannot tell you whether the account exists."""
    if request.user.is_authenticated:
        return redirect("accounts:change_password")
    return render(request, "accounts/forgot_sent.html")


def reset_with_code(request):
    """Choose a new password with the code the Super Admin gave you."""
    if request.user.is_authenticated:
        return redirect("accounts:change_password")

    form = ResetWithCodeForm(request.POST or None, initial={"username": request.session.get("reset_username", "")})
    if request.method == "POST" and form.is_valid():
        user = recovery.find_user(form.cleaned_data["username"])
        if user and recovery.spend_code(user, form.cleaned_data["code"]):
            user.set_password(form.cleaned_data["new_password1"])
            user.must_change_password = False
            user.save(update_fields=["password", "must_change_password"])
            # Anything asked for earlier is dead now.
            user.reset_codes.filter(used_at__isnull=True).update(used_at=timezone.now())
            request.session.pop("reset_username", None)
            return redirect(f"{reverse('accounts:login')}?reset=done")
        form.add_error(None, "That code is not right, or it has expired. Check it, or go back and ask for a new one.")
    return render(request, "accounts/reset_with_code.html", {"form": form})


@super_admin_only
@require_POST
def employee_phone(request, pk):
    """Register (or clear) a mobile number — the one a Super Admin's reset code is texted to."""
    employee = get_object_or_404(User, pk=pk, is_active=True)
    typed = request.POST.get("phone", "").strip()
    number = sms.mobile_digits(typed)
    if typed and not number:
        messages.error(request, "That is not a 10-digit mobile number.")
    else:
        employee.phone = number
        employee.save(update_fields=["phone"])
        messages.success(
            request,
            f"{employee.display_name}'s mobile number saved." if number else f"{employee.display_name}'s mobile number removed.",
        )
    return redirect("accounts:employee_list")
