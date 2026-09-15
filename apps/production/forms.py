from django import forms
from django.forms import inlineformset_factory

from apps.production.models import ProductionSheet, ProductionSheetItem, ProductionTask, QualityCheck

ProductionSheetItemFormSet = inlineformset_factory(
    ProductionSheet, ProductionSheetItem,
    fields=[
        "window_door_number", "quantity", "width", "height", "profile", "colour", "glass", "glass_thickness",
        "hardware", "handle", "reinforcement", "mesh", "accessories", "opening_direction",
        "manufacturing_specs", "installation_requirements",
    ],
    extra=1, can_delete=True,
)


class ProductionTaskUpdateForm(forms.ModelForm):
    class Meta:
        model = ProductionTask
        fields = ["assigned_to", "status", "remarks"]


class QualityCheckForm(forms.ModelForm):
    class Meta:
        model = QualityCheck
        fields = ["status", "remarks"]
        widgets = {"remarks": forms.Textarea(attrs={"rows": 2})}
