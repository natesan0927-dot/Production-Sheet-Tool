from django import forms

from apps.logistics.models import Dispatch, Installation, SiteNotReadyLog


class DispatchForm(forms.ModelForm):
    class Meta:
        model = Dispatch
        fields = [
            "dispatch_date", "vehicle_number", "driver", "driver_phone", "transporter",
            "number_of_packages", "package_details", "delivery_address", "expected_delivery_date", "remarks",
        ]
        widgets = {
            "dispatch_date": forms.DateInput(attrs={"type": "date"}),
            "expected_delivery_date": forms.DateInput(attrs={"type": "date"}),
            "package_details": forms.Textarea(attrs={"rows": 2}),
            "delivery_address": forms.Textarea(attrs={"rows": 2}),
            "remarks": forms.Textarea(attrs={"rows": 2}),
        }


class InstallationForm(forms.ModelForm):
    class Meta:
        model = Installation
        fields = ["team_leader", "installation_team", "scheduled_date", "site_readiness", "remarks"]
        widgets = {
            "scheduled_date": forms.DateInput(attrs={"type": "date"}),
            "installation_team": forms.CheckboxSelectMultiple,
            "remarks": forms.Textarea(attrs={"rows": 2}),
        }


class SiteNotReadyForm(forms.ModelForm):
    class Meta:
        model = SiteNotReadyLog
        fields = ["reason", "other_text", "rescheduled_to"]
        widgets = {"rescheduled_to": forms.DateInput(attrs={"type": "date"})}


class HandoverForm(forms.Form):
    customer_confirmation = forms.BooleanField(required=False, initial=True, label="Customer confirms installation")
    remarks = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)
    customer_signature = forms.ImageField(required=False)
