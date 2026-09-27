"""Adding staff, and letting them pick their own password."""

import re

from django import forms
from django.contrib.auth.forms import PasswordChangeForm

from .models import Role, User

# What every new account starts on. They are made to change it at first sign-in.
DEFAULT_PASSWORD = "ChangeMe@123"

CONTROL = {"class": "form-control"}
SELECT = {"class": "form-select"}


class EmployeeForm(forms.ModelForm):
    """Name and role. The username and the starting password follow from those."""

    full_name = forms.CharField(label="Name", max_length=150, widget=forms.TextInput(attrs=CONTROL))

    field_order = ["full_name", "role", "phone"]

    class Meta:
        model = User
        fields = ["role", "phone"]
        widgets = {"role": forms.Select(attrs=SELECT), "phone": forms.TextInput(attrs=CONTROL)}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone"].required = False
        self.fields["phone"].widget.attrs["placeholder"] = "Optional"
        if self.instance.pk:
            self.fields["full_name"].initial = self.instance.get_full_name()

    def clean_full_name(self):
        name = " ".join(self.cleaned_data["full_name"].split())
        if not name:
            raise forms.ValidationError("Give the employee a name.")
        return name

    @staticmethod
    def username_for(name):
        """A short sign-in name from the person's own — unique, lower case."""
        base = re.sub(r"[^a-z0-9]+", "", name.split()[0].lower()) or "staff"
        candidate, suffix = base, 2
        while User.objects.filter(username=candidate).exists():
            candidate, suffix = f"{base}{suffix}", suffix + 1
        return candidate

    def save(self, commit=True):
        employee = super().save(commit=False)
        name = self.cleaned_data["full_name"].split()
        employee.first_name = name[0]
        employee.last_name = " ".join(name[1:])
        if not employee.pk:
            employee.username = self.username_for(self.cleaned_data["full_name"])
            employee.set_password(DEFAULT_PASSWORD)
            employee.must_change_password = True
            # The Super Admin is the one account that needs the Django admin.
            if employee.role == Role.SUPER_ADMIN:
                employee.is_staff = employee.is_superuser = True
        if commit:
            employee.save()
        return employee


class FirstPasswordForm(PasswordChangeForm):
    """The change-password form, dressed to match the rest of the app.

    On the forced first change there is no "current password" box. The person
    signed in with the shared default seconds ago, so asking for it again proves
    nothing and gives one more place to fail — a mistyped character, a browser
    filling the box with some other saved password — after which the screen says
    the password they were just given is wrong. Later changes, from the ordinary
    page, still ask for it.
    """

    def __init__(self, user, *args, forced=False, **kwargs):
        super().__init__(user, *args, **kwargs)
        if forced:
            del self.fields["old_password"]
        else:
            self.fields["old_password"].label = "Current password"
        for field in self.fields.values():
            field.widget.attrs.update(CONTROL)
        self.fields["new_password1"].label = "New password"
        self.fields["new_password2"].label = "New password again"

    def clean_new_password1(self):
        chosen = self.cleaned_data["new_password1"]
        if chosen == DEFAULT_PASSWORD:
            raise forms.ValidationError("Pick something other than the password you were given.")
        return chosen
