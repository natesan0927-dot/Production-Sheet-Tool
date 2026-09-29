"""Staff records, and the password every new account has to set for itself."""

from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import recovery, sms, switching
from .forms import DEFAULT_PASSWORD, EmployeeForm, FirstPasswordForm, ForgotPasswordForm, MobileForm, ResetWithCodeForm
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
    # Their open leads stay under their name until someone else takes them on,
    # and nobody is chasing them in the meantime.
    open_leads = employee.leads.filter(status="open").count()
    if open_leads:
        messages.warning(
            request,
            f"{employee.display_name} still has {open_leads} open lead{'s' if open_leads != 1 else ''}. "
            "Reassign them from Leads (filter by their name) so their follow-ups are not missed.",
        )
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
        form.add_error(None, "That OTP is not right, or it has expired. Check it, or go back and send a new one.")
    return render(request, "accounts/reset_with_code.html", {"form": form})


@login_required
def profile(request):
    """Your own account: who you are, your password, and your mobile number.

    The Super Admin's number is where the OTP for a forgotten password is texted,
    so it is only registered once an OTP sent to it has been typed back.
    """
    user = request.user
    if request.method == "POST":
        action = request.POST.get("action", "")
        if user.is_super_admin and action == "verify":
            if recovery.finish_phone_check(user, request.POST.get("otp", "")):
                messages.success(request, f"{user.phone} is registered. An OTP for a forgotten password will be texted to it.")
            else:
                messages.error(request, "That OTP is not right, or it has expired. Check it, or send a new one.")
            return redirect("accounts:profile")
        if user.is_super_admin and action == "resend":
            number = recovery.pending_phone(user)
            if number:
                _texted(request, *recovery.start_phone_check(user, number), number)
            return redirect("accounts:profile")
        if user.is_super_admin and action == "cancel":
            user.reset_codes.filter(purpose="verify", used_at__isnull=True).update(used_at=timezone.now())
            return redirect("accounts:profile")

        form = MobileForm(user, request.POST)
        if form.is_valid():
            number = form.cleaned_data["phone"]
            if user.is_super_admin:
                _texted(request, *recovery.start_phone_check(user, number), number)
            else:
                user.phone = number
                user.save(update_fields=["phone"])
                messages.success(request, "Mobile number saved.")
            return redirect("accounts:profile")
    else:
        form = MobileForm(user, initial={"phone": user.phone})

    pending = recovery.pending_phone(user) if user.is_super_admin else ""
    return render(
        request,
        "accounts/profile.html",
        {
            "form": form,
            "pending": pending,
            "pending_masked": sms.masked(pending),
            "sms_ready": sms.configured(),
        },
    )


@require_POST
def switch_account(request, pk):
    """Use another account already signed in on this device — no password while it is still signed in."""
    listed = switching.entries(request)
    entry = next((item for item in listed if item["u"] == pk), None)
    if entry is None:
        return redirect("accounts:login")

    user = switching.switch_to(request, pk)
    if user is None:
        # Their session has ended (or their password changed): they sign in again.
        messages.info(request, f"{entry['n']} has been signed out on this device. Sign in again to switch to them.")
        params = {"username": User.objects.filter(pk=pk).values_list("username", flat=True).first() or ""}
        if request.user.is_authenticated:
            params["add"] = "1"
        response = redirect(f"{reverse('accounts:login')}?{urlencode(params)}")
        switching.write(response, [item for item in listed if item["u"] != pk])
        return response

    messages.success(request, f"Switched to {user.display_name}.")
    return redirect("crm:dashboard")


@require_POST
def logout_everyone(request):
    """Sign out of every account on this device at once — for handing the device on."""
    switching.forget_all(request)
    logout(request)
    response = redirect("accounts:login")
    switching.write(response, [])
    return response


def _texted(request, sent, reason, number):
    if sent:
        messages.success(request, f"An OTP has been texted to {sms.masked(number)}. Type it below to register the number.")
    else:
        messages.error(request, reason)


@super_admin_only
@require_POST
def employee_phone(request, pk):
    """Register (or clear) a member of staff's mobile number."""
    employee = get_object_or_404(User, pk=pk, is_active=True)
    if employee.is_super_admin:
        # Where their reset OTP goes: registered by them, proved with an OTP, in their profile.
        messages.error(request, "A Super Admin registers their own mobile number in My profile, where it is checked with an OTP.")
        return redirect("accounts:employee_list")
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
