from django import forms
from django.forms import inlineformset_factory

from apps.measurement.models import FinalMeasurementItem, FinalMeasurementRequest, MeasurementItem, MeasurementRequest


class MeasurementRequestForm(forms.ModelForm):
    class Meta:
        model = MeasurementRequest
        fields = ["site_address", "contact_person", "assigned_to", "scheduled_date", "priority", "instructions", "remarks"]
        widgets = {
            "site_address": forms.Textarea(attrs={"rows": 2}),
            "scheduled_date": forms.DateInput(attrs={"type": "date"}),
            "instructions": forms.Textarea(attrs={"rows": 2}),
            "remarks": forms.Textarea(attrs={"rows": 2}),
        }


MeasurementItemFormSet = inlineformset_factory(
    MeasurementRequest, MeasurementItem,
    fields=[
        "window_number", "room_location", "width", "height", "quantity", "window_type", "door_type",
        "opening_type", "glass_type", "glass_thickness", "profile_series", "profile_colour",
        "hardware", "handle_type", "mesh", "reinforcement", "remarks",
    ],
    extra=1, can_delete=True,
)


class FinalMeasurementRequestForm(forms.ModelForm):
    class Meta:
        model = FinalMeasurementRequest
        fields = ["assigned_to", "scheduled_date", "site_readiness", "special_remarks"]
        widgets = {
            "scheduled_date": forms.DateInput(attrs={"type": "date"}),
            "special_remarks": forms.Textarea(attrs={"rows": 2}),
        }


FinalMeasurementItemFormSet = inlineformset_factory(
    FinalMeasurementRequest, FinalMeasurementItem,
    fields=[
        "window_number", "final_width", "final_height", "opening_direction", "frame_details", "sash_details",
        "glass_details", "hardware_details", "colour", "profile", "reinforcement", "mesh", "accessories",
        "installation_requirements", "remarks",
    ],
    extra=1, can_delete=True,
)
