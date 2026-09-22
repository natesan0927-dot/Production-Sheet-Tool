from django.contrib.auth import views as auth_views
from django.urls import path

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
        context = super().get_context_data(**kwargs)
        context["demo_accounts"] = DEMO_ACCOUNTS
        return context


urlpatterns = [
    path("login/", TitansLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
