from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

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
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        from .models import User

        context = super().get_context_data(**kwargs)
        context["reset_done"] = self.request.GET.get("reset") == "done"
        # Only offered while the demo accounts are actually installed, so a
        # live site never shows a row of one-click logins.
        usernames = [username for username, *_ in DEMO_ACCOUNTS]
        if User.objects.filter(username__in=usernames).exists():
            context["demo_accounts"] = DEMO_ACCOUNTS
        return context


urlpatterns = [
    path("login/", TitansLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("password/", views.change_password, name="change_password"),
    path("forgot/", views.forgot_password, name="forgot_password"),
    path("forgot/reset/", views.reset_with_code, name="reset_with_code"),
    path("employees/<int:pk>/phone/", views.employee_phone, name="employee_phone"),
    path("employees/", views.employee_list, name="employee_list"),
    path("employees/<int:pk>/reset/", views.employee_reset, name="employee_reset"),
    path("employees/<int:pk>/remove/", views.employee_remove, name="employee_remove"),
]
