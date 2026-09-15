from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.accounts.forms import EmployeeCreateForm, EmployeeUpdateForm
from apps.accounts.models import User
from apps.core.demo_data import DEMO_ICONS, DEMO_PASSWORD, DEMO_USERS
from apps.core.mixins import RoleRequiredMixin


class TitansLoginView(auth_views.LoginView):
    template_name = "accounts/login.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["demo_accounts"] = [
            {
                "username": username, "password": DEMO_PASSWORD, "label": group_name,
                "name": f"{first_name} {last_name}", "icon": DEMO_ICONS.get(group_name, "fa-user"),
            }
            for username, group_name, first_name, last_name, _is_staff in DEMO_USERS
        ]
        return ctx


@login_required
def my_profile(request):
    return render(request, "accounts/profile.html", {"employee": request.user})


class EmployeeListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    model = User
    template_name = "accounts/employee_list.html"
    context_object_name = "employees"
    paginate_by = 50
    section = "people"

    def get_queryset(self):
        qs = User.objects.select_related("department").order_by("first_name", "last_name")
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(username__icontains=q) | qs.filter(first_name__icontains=q) | qs.filter(
                last_name__icontains=q
            ) | qs.filter(employee_id__icontains=q)
        return qs


class EmployeeDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    model = User
    template_name = "accounts/employee_detail.html"
    context_object_name = "employee"
    section = "people"


class EmployeeCreateView(LoginRequiredMixin, RoleRequiredMixin, CreateView):
    model = User
    form_class = EmployeeCreateForm
    template_name = "accounts/employee_form.html"
    section = "people"

    def get_success_url(self):
        messages.success(self.request, "Employee created.")
        return reverse_lazy("accounts:employee_detail", args=[self.object.pk])


class EmployeeUpdateView(LoginRequiredMixin, RoleRequiredMixin, UpdateView):
    model = User
    form_class = EmployeeUpdateForm
    template_name = "accounts/employee_form.html"
    section = "people"

    def get_success_url(self):
        messages.success(self.request, "Employee updated.")
        return reverse_lazy("accounts:employee_detail", args=[self.object.pk])
