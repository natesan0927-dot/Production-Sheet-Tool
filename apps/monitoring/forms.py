from decimal import Decimal

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils import timezone

from apps.accounts.models import Role

from .models import Advance, Worker

CONTROL = {"class": "form-control"}


class MonitoringLoginForm(AuthenticationForm):
    """Only the Super Admin and the sales executives may sign in to Monitoring."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "not_monitoring": "Monitoring is only for the Super Admin and the sales executives.",
    }

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.role not in (Role.SUPER_ADMIN, Role.SALESPERSON):
            raise forms.ValidationError(self.error_messages["not_monitoring"], code="not_monitoring")


class WorkerForm(forms.ModelForm):
    class Meta:
        model = Worker
        fields = ["name", "phone", "designation", "joined_on", "monthly_salary", "opening_advance", "address", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={**CONTROL, "autofocus": True}),
            "phone": forms.TextInput(attrs={**CONTROL, "inputmode": "tel"}),
            "designation": forms.TextInput(attrs=CONTROL),
            "joined_on": forms.DateInput(attrs={**CONTROL, "type": "date"}),
            "monthly_salary": forms.NumberInput(attrs={**CONTROL, "min": "0", "step": "0.01", "inputmode": "decimal"}),
            "opening_advance": forms.NumberInput(attrs={**CONTROL, "min": "0", "step": "0.01", "inputmode": "decimal"}),
            "address": forms.Textarea(attrs={**CONTROL, "rows": 2}),
            "notes": forms.Textarea(attrs={**CONTROL, "rows": 2}),
        }
        labels = {"monthly_salary": "Monthly salary (₹)", "opening_advance": "Advance already outstanding (₹)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["joined_on"].widget.attrs["max"] = timezone.localdate().isoformat()

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean_monthly_salary(self):
        salary = self.cleaned_data["monthly_salary"]
        if salary is not None and salary <= 0:
            raise forms.ValidationError("Enter the monthly salary.")
        return salary

    def clean_opening_advance(self):
        amount = self.cleaned_data.get("opening_advance") or Decimal("0")
        if amount < 0:
            raise forms.ValidationError("An advance cannot be less than nothing.")
        return amount

    def clean_joined_on(self):
        day = self.cleaned_data.get("joined_on")
        if day and day > timezone.localdate():
            raise forms.ValidationError("The joining date cannot be in the future.")
        return day


class AdvanceForm(forms.ModelForm):
    """The three figures a month's advances are made of. Editable until the month closes."""

    class Meta:
        model = Advance
        fields = ["monthly_advance", "weekly_advance", "deduction"]
        widgets = {name: forms.NumberInput(attrs={**CONTROL, "min": "0", "step": "0.01", "inputmode": "decimal"})
                   for name in ["monthly_advance", "weekly_advance", "deduction"]}
        labels = {
            "monthly_advance": "Advance received this month (₹)",
            "weekly_advance": "Weekly advance for this month (₹)",
            "deduction": "Amount to deduct (₹)",
        }

    def __init__(self, *args, previous=Decimal("0"), **kwargs):
        super().__init__(*args, **kwargs)
        self.previous = previous

    def clean(self):
        data = super().clean()
        for name in ["monthly_advance", "weekly_advance", "deduction"]:
            value = data.get(name)
            if value is None:
                data[name] = Decimal("0")
            elif value < 0:
                self.add_error(name, "Enter 0 or more.")
        owed = self.previous + data.get("monthly_advance", 0) + data.get("weekly_advance", 0)
        if data.get("deduction", 0) > owed:
            self.add_error("deduction", f"That is more than the ₹{owed:,.2f} of advance they owe.")
        return data
