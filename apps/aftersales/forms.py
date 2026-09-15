from django import forms

from apps.aftersales.models import ServiceComplaint


class ServiceComplaintForm(forms.ModelForm):
    class Meta:
        model = ServiceComplaint
        fields = [
            "customer", "order", "category", "product", "description", "priority",
            "assigned_technician", "scheduled_date", "is_warranty",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "scheduled_date": forms.DateInput(attrs={"type": "date"}),
        }


class ServiceComplaintUpdateForm(forms.ModelForm):
    class Meta:
        model = ServiceComplaint
        fields = [
            "status", "assigned_technician", "scheduled_date", "resolution",
            "spare_parts", "service_charges", "completion_date",
        ]
        widgets = {
            "resolution": forms.Textarea(attrs={"rows": 2}),
            "scheduled_date": forms.DateInput(attrs={"type": "date"}),
            "completion_date": forms.DateInput(attrs={"type": "date"}),
        }
