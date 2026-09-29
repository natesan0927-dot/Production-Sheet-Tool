from django.contrib.auth import views as auth_views
from django.urls import path

from . import switching, views

app_name = "accounts"

# username, tile label, person's name, icon
DEMO_ACCOUNTS = [
    ("demo_sales1", "Salesperson", "Arun Kumar", "fa-user-tie"),
    ("demo_sales2", "Salesperson", "Priya Raman", "fa-user-tie"),
    ("demo_measure", "Measurement", "Vignesh S", "fa-ruler-combined"),
    ("demo_quotation", "Quotation", "Deepa R", "fa-file-invoice"),
    ("demo_accounts", "Accounts", "Lakshmi N", "fa-file-invoice"),
    ("demo_production", "Production", "Karthik M", "fa-industry"),
    ("demo_field", "Field Manager", "Suresh P", "fa-shield-halved"),
    ("demo_admin", "Super Admin", "Titans Admin", "fa-crown"),
]


class TitansLoginView(auth_views.LoginView):
    """Signing in — or, with ?add=1, signing in someone else as well, like adding a Google account."""

    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def adding(self):
        return self.request.user.is_authenticated and "1" in (self.request.GET.get("add"), self.request.POST.get("add"))

    def dispatch(self, request, *args, **kwargs):
        # Someone already signed in is only sent on when they are not adding another account.
        self.redirect_authenticated_user = not self.adding()
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {**super().get_initial(), "username": self.request.GET.get("username", "")}

    def form_valid(self, form):
        if self.adding() and form.get_user().pk != self.request.user.pk:
            # A new session for them, so the one already signed in here stays signed in.
            switching.detach(self.request)
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        from .models import User

        context = super().get_context_data(**kwargs)
        context["reset_done"] = self.request.GET.get("reset") == "done"
        context["adding"] = self.adding()
        me = self.request.user.pk if self.request.user.is_authenticated else None
        context["accounts_here"] = [entry for entry in switching.signed_in_here(self.request) if entry["u"] != me]
        # Only offered while the demo accounts are actually installed, so a
        # live site never shows a row of one-click logins.
        usernames = [username for username, *_ in DEMO_ACCOUNTS]
        if not context["adding"] and User.objects.filter(username__in=usernames).exists():
            context["demo_accounts"] = DEMO_ACCOUNTS
        return context


class TitansLogoutView(auth_views.LogoutView):
    """Signs out the account in use. Anyone else signed in on this device stays signed in."""

    def post(self, request, *args, **kwargs):
        key = request.session.session_key
        listed = switching.entries(request)
        response = super().post(request, *args, **kwargs)
        switching.write(response, [entry for entry in listed if entry["k"] != key])
        return response


urlpatterns = [
    path("login/", TitansLoginView.as_view(), name="login"),
    path("logout/", TitansLogoutView.as_view(), name="logout"),
    path("logout/everyone/", views.logout_everyone, name="logout_everyone"),
    path("switch/<int:pk>/", views.switch_account, name="switch_account"),
    path("password/", views.change_password, name="change_password"),
    path("profile/", views.profile, name="profile"),
    path("forgot/", views.forgot_password, name="forgot_password"),
    path("forgot/sent/", views.forgot_sent, name="forgot_sent"),
    path("forgot/reset/", views.reset_with_code, name="reset_with_code"),
    path("employees/<int:pk>/set-password/", views.employee_set_password, name="employee_set_password"),
    path("employees/<int:pk>/dismiss-request/", views.employee_dismiss_request, name="employee_dismiss_request"),
    path("employees/<int:pk>/phone/", views.employee_phone, name="employee_phone"),
    path("employees/", views.employee_list, name="employee_list"),
    path("employees/<int:pk>/reset/", views.employee_reset, name="employee_reset"),
    path("employees/<int:pk>/remove/", views.employee_remove, name="employee_remove"),
]
