from datetime import time

from django import forms
from django.utils import timezone

from apps.accounts.models import Role, User

from .models import FollowUp, Lead, Payment, SalesTarget, Task


class BootstrapMixin:
    """Gives every widget the right Bootstrap class without per-field noise."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.RadioSelect, forms.CheckboxSelectMultiple)):
                continue
            if isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(item, initial) for item in data]
        return [single(data, initial)]


class LeadForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Lead
        fields = [
            "customer_name",
            "phone",
            "site_location",
            "lead_source",
            "lead_source_other",
            "assigned_to",
            "approx_quantity",
            "expected_value",
            "site_stage",
            "remarks",
        ]
        widgets = {"remarks": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = User.objects.filter(role=Role.SALESPERSON, is_active=True)
        self.fields["lead_source_other"].widget.attrs["placeholder"] = "Where did this lead come from?"
        # A salesperson only ever files leads under their own name.
        if user and user.role == Role.SALESPERSON:
            self.fields["assigned_to"].initial = user
            self.fields["assigned_to"].disabled = True

    def clean(self):
        data = super().clean()
        if data.get("lead_source") == "other" and not data.get("lead_source_other"):
            self.add_error("lead_source_other", "Tell us where this lead came from.")
        elif data.get("lead_source") != "other":
            data["lead_source_other"] = ""
        return data


class MeasurementBoxForm(forms.Form):
    """Stage 1's measurements box: upload, type it out, or ask the measurement team."""

    mode = forms.ChoiceField(choices=Lead.MeasurementMode.choices, widget=forms.RadioSelect)
    file = forms.FileField(required=False, widget=forms.ClearableFileInput(attrs={"class": "form-control"}))
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "class": "form-control", "placeholder": "Type the measurements here"}),
    )

    def clean(self):
        data = super().clean()
        mode = data.get("mode")
        if mode == Lead.MeasurementMode.FILE and not data.get("file"):
            self.add_error("file", "Choose the measurement file to upload.")
        if mode == Lead.MeasurementMode.TEXT and not data.get("notes"):
            self.add_error("notes", "Type the measurements, or pick another option.")
        return data


class RoughMeasurementForm(forms.Form):
    """What the measurement staff submits for a requested rough measurement."""

    file = forms.FileField(required=False, widget=forms.ClearableFileInput(attrs={"class": "form-control"}))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4, "class": "form-control"}))

    def clean(self):
        data = super().clean()
        if not data.get("file") and not data.get("notes"):
            raise forms.ValidationError("Upload the measurement file or type the measurements.")
        return data


class QuotationForm(forms.Form):
    quotation_number = forms.CharField(
        max_length=60,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter the quotation number"}),
    )
    files = MultipleFileField(label="Quotation file(s)")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["files"].widget.attrs.setdefault("class", "form-control")


class WonForm(BootstrapMixin, forms.ModelForm):
    """Confirming the order also captures what the factory needs later."""

    class Meta:
        model = Lead
        fields = [
            "order_value",
            "advance_received",
            "committed_delivery_date",
            "window_count",
            "total_sqft",
            "won_remarks",
        ]
        widgets = {
            "committed_delivery_date": forms.DateInput(attrs={"type": "date"}),
            "won_remarks": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {"won_remarks": "Remarks"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("order_value", "advance_received", "committed_delivery_date", "window_count", "total_sqft"):
            self.fields[name].required = True


class LostForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Lead
        fields = ["lost_reason", "lost_price_elsewhere"]
        widgets = {"lost_reason": forms.Textarea(attrs={"rows": 3})}
        labels = {"lost_reason": "Reason"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lost_reason"].required = True


class CafFinalForm(forms.Form):
    """Stage 5 — the signed CAF and the final measurement, uploaded together."""

    caf_signed = forms.FileField(
        label="Signed CAF", required=False, widget=forms.ClearableFileInput(attrs={"class": "form-control"})
    )
    final_measurement = forms.FileField(
        label="Final measurement file", required=False, widget=forms.ClearableFileInput(attrs={"class": "form-control"})
    )

    def clean(self):
        data = super().clean()
        caf, final = data.get("caf_signed"), data.get("final_measurement")
        if not caf and not final:
            raise forms.ValidationError("Upload the signed CAF and the final measurement file.")
        if not caf:
            self.add_error("caf_signed", "Upload the signed CAF together with the final measurement.")
        if not final:
            self.add_error("final_measurement", "Upload the final measurement together with the signed CAF.")
        return data


class SingleFileForm(forms.Form):
    file = forms.FileField(widget=forms.ClearableFileInput(attrs={"class": "form-control"}))


class ChecklistForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = Lead.CHECKLIST_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-check-input")


class DispatchForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Lead
        fields = ["installation_person", "invoice_number", "invoice_date"]
        widgets = {"invoice_date": forms.DateInput(attrs={"type": "date"})}
        labels = {"installation_person": "Installation person name"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = True


class FollowUpForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = FollowUp
        fields = ["date", "time", "note"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].initial = timezone.localdate()
        self.fields["time"].initial = time(9, 0)


class PaymentForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["paid_on", "amount", "remarks", "file"]
        widgets = {"paid_on": forms.DateInput(attrs={"type": "date"})}
        labels = {"paid_on": "Payment date"}


class LedgerForm(BootstrapMixin, forms.ModelForm):
    """Lets accounts correct the headline figures on a confirmed order."""

    class Meta:
        model = Lead
        fields = ["order_value", "advance_received", "invoice_number", "invoice_date"]
        widgets = {"invoice_date": forms.DateInput(attrs={"type": "date"})}


class TaskForm(BootstrapMixin, forms.ModelForm):
    """Assign a to-do to anyone — including yourself."""

    class Meta:
        model = Task
        fields = ["assigned_to", "title", "due_date", "details"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "details": forms.Textarea(attrs={"rows": 2, "placeholder": "Anything else they should know (optional)"}),
        }
        labels = {"assigned_to": "Assign to", "title": "What needs doing"}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        people = User.objects.filter(is_active=True)
        self.fields["assigned_to"].queryset = people
        self.fields["assigned_to"].label_from_instance = lambda u: f"{u.get_full_name() or u.username} — {u.get_role_display()}"
        if user:
            self.fields["assigned_to"].initial = user


class StageAccessForm(forms.Form):
    """Super Admin: which stages of the lead journey this employee may see."""

    def __init__(self, *args, stage_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["stages"] = forms.MultipleChoiceField(
            choices=stage_choices,
            required=False,
            widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
            label="Stages this employee can see",
            help_text="Leave every box unticked to fall back to the default for their role.",
        )


class SalesTargetForm(BootstrapMixin, forms.ModelForm):
    month = forms.DateField(
        label="Select month",
        input_formats=["%Y-%m", "%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "month"}),
    )

    class Meta:
        model = SalesTarget
        fields = ["salesperson", "month", "amount"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["salesperson"].queryset = User.objects.filter(role=Role.SALESPERSON, is_active=True)
        if user and user.role == Role.SALESPERSON:
            self.fields["salesperson"].initial = user
            self.fields["salesperson"].disabled = True
