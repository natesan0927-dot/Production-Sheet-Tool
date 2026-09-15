from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.models import Group

from apps.accounts.models import User


class EmployeeCreateForm(UserCreationForm):
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(), required=False, widget=forms.CheckboxSelectMultiple, help_text="Role(s)"
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username", "employee_id", "first_name", "last_name", "email", "mobile",
            "department", "designation", "is_active", "groups",
        )

    def save(self, commit=True):
        user = super().save(commit)
        if commit:
            user.groups.set(self.cleaned_data["groups"])
        return user


class EmployeeUpdateForm(UserChangeForm):
    password = None
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(), required=False, widget=forms.CheckboxSelectMultiple, help_text="Role(s)"
    )

    class Meta(UserChangeForm.Meta):
        model = User
        fields = (
            "username", "employee_id", "first_name", "last_name", "email", "mobile",
            "department", "designation", "is_active", "groups", "photo",
        )

    def save(self, commit=True):
        user = super().save(commit)
        if commit:
            user.groups.set(self.cleaned_data["groups"])
        return user
