"""Adding staff, and letting them pick their own password."""

import re

from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import ValidationError

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
        # Whatever they were given — the shared default, or one the Super Admin set
        # when they forgot theirs — is only ever a way in, never the password kept.
        if chosen == DEFAULT_PASSWORD or self.user.check_password(chosen):
            raise forms.ValidationError("Pick something other than the password you were given.")
        return chosen


class MobileForm(forms.Form):
    """A new mobile number for the profile.

    The Super Admin's is where a forgotten password's OTP goes, so changing it
    takes their current password too: a desk left signed in must not be enough
    to redirect it.
    """

    phone = forms.CharField(
        label="Mobile number", max_length=20,
        widget=forms.TextInput(attrs={"class": "form-control", "inputmode": "tel", "autocomplete": "tel",
                                      "placeholder": "10-digit mobile number"}),
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user.is_super_admin:
            self.fields["current_password"] = forms.CharField(
                label="Your current password", strip=False,
                widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "current-password"}),
            )

    def clean_phone(self):
        from .sms import mobile_digits

        number = mobile_digits(self.cleaned_data["phone"])
        if not number:
            raise forms.ValidationError("Enter a 10-digit Indian mobile number.")
        return number

    def clean_current_password(self):
        typed = self.cleaned_data["current_password"]
        if not self.user.check_password(typed):
            raise forms.ValidationError("That is not your current password.")
        return typed


NAME_BOX = {"class": "form-control", "autocomplete": "username", "autocapitalize": "none", "autocorrect": "off", "spellcheck": "false"}


class ForgotPasswordForm(forms.Form):
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={**NAME_BOX, "autofocus": True}))


class ResetWithCodeForm(forms.Form):
    """The username, the code from the Super Admin, and the new password."""

    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs=NAME_BOX))
    code = forms.RegexField(
        r"^\s*\d{6}\s*$",
        label="OTP",
        error_messages={"invalid": "The OTP is six digits."},
        widget=forms.TextInput(attrs={"class": "form-control", "inputmode": "numeric", "autocomplete": "one-time-code", "maxlength": "8"}),
    )
    new_password1 = forms.CharField(label="New password", strip=False, widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}))
    new_password2 = forms.CharField(label="New password again", strip=False, widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}))

    def clean(self):
        data = super().clean()
        first, second = data.get("new_password1"), data.get("new_password2")
        if first and second and first != second:
            self.add_error("new_password2", "The two passwords do not match.")
        elif first:
            if first == DEFAULT_PASSWORD:
                self.add_error("new_password1", "Pick something other than the password you were given.")
            else:
                # Checked before the code is used, so a weak choice does not cost
                # anyone their code. Checked against the name as typed, never the
                # account on file: the answer must read the same whether or not that
                # account exists, or this page would tell a stranger who works here.
                typed = (data.get("username") or "").strip()
                try:
                    password_validation.validate_password(first, User(username=typed))
                except ValidationError as problem:
                    self.add_error("new_password1", problem)
        return data
