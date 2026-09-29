import re
from datetime import time, timedelta

from django import forms
from django.conf import settings
from django.utils import timezone

from apps.accounts.models import Role, User

from .models import FollowUp, InstallerPayment, InvoiceCharge, Lead, Payment, SalesTarget, ServiceComplaint, Task

# ---------------------------------------------------------------------------
# Sanity checks shared by every form. Each adds an error against the field
# rather than raising, so all the problems on a form are reported at once.
# ---------------------------------------------------------------------------


def _today():
    return timezone.localdate()


def measurement_staff():
    """Everyone who can be sent out to measure a site."""
    return User.objects.filter(role=Role.MEASUREMENT, is_active=True).order_by("first_name", "username")


def reject_future(form, name, label):
    value = form.cleaned_data.get(name)
    if value and value > _today():
        form.add_error(name, f"{label} can't be in the future.")


def reject_past(form, name, label):
    value = form.cleaned_data.get(name)
    if value and value < _today():
        form.add_error(name, f"{label} can't be in the past.")


def reject_before_order(form, name, label, lead):
    value = form.cleaned_data.get(name)
    if value and lead is not None and lead.won_at and value < timezone.localdate(lead.won_at):
        form.add_error(name, f"{label} can't be before the order was confirmed ({timezone.localdate(lead.won_at):%d %b %Y}).")


def require_positive(form, name, label):
    value = form.cleaned_data.get(name)
    if value is not None and value <= 0:
        form.add_error(name, f"{label} must be more than zero.")


def reject_negative(form, name, label):
    value = form.cleaned_data.get(name)
    if value is not None and value < 0:
        form.add_error(name, f"{label} can't be negative.")


def limit_picker(field, *, not_before_today=False, not_after_today=False):
    """Mirror the rule in the browser's date picker so bad dates can't be chosen."""
    today = _today().isoformat()
    if not_before_today:
        field.widget.attrs["min"] = today
    if not_after_today:
        field.widget.attrs["max"] = today


def limit_number(field, minimum):
    field.widget.attrs["min"] = str(minimum)


def check_upload_size(upload):
    """A phone video or a raw scan can be hundreds of megabytes; the bucket is not."""
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    if upload and getattr(upload, "size", 0) > limit:
        raise forms.ValidationError(
            f"{upload.name} is {upload.size / 1024 / 1024:.0f} MB. Files can be up to {settings.MAX_UPLOAD_MB} MB — "
            "save it as a PDF, or use Scan to make one."
        )


def limit_uploads(form):
    """Every file box on the form gets the size check."""
    for field in form.fields.values():
        if isinstance(field, forms.FileField) and check_upload_size not in field.validators:
            field.validators.append(check_upload_size)


def sales_executive_choices():
    """Everyone a lead or a target can sit under — the Super Admin works leads of their own."""
    return User.objects.filter(role__in=[Role.SALESPERSON, Role.SUPER_ADMIN], is_active=True).order_by(
        "role", "first_name", "username"
    )


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
            "salutation",
            "customer_name",
            "phone",
            "project_name",
            "site_location",
            "site_map_link",
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
        self.fields["assigned_to"].queryset = sales_executive_choices()
        # Statements and certificates address the customer as Mr., Mrs. and so on,
        # so it is asked for once, here, and not guessed from a name.
        self.fields["salutation"].required = True
        self.fields["salutation"].choices = [("", "Choose…")] + list(Lead.Salutation.choices)
        self.fields["lead_source_other"].widget.attrs["placeholder"] = "Where did this lead come from?"
        self.fields["phone"].widget.attrs.update({"inputmode": "tel", "placeholder": "10-digit mobile number"})
        self.fields["project_name"].widget.attrs["placeholder"] = "Optional — printed on the CAF"
        self.fields["site_map_link"].widget.attrs["placeholder"] = "Optional — paste the Google Maps link"
        limit_number(self.fields["approx_quantity"], 1)
        limit_number(self.fields["expected_value"], 1)
        # A salesperson only ever files leads under their own name.
        if user and user.role == Role.SALESPERSON:
            self.fields["assigned_to"].initial = user
            self.fields["assigned_to"].disabled = True

    def clean_phone(self):
        digits = re.sub(r"\D", "", self.cleaned_data["phone"])
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        elif len(digits) == 11 and digits.startswith("0"):
            digits = digits[1:]
        if len(digits) != 10:
            raise forms.ValidationError("Enter a valid 10-digit phone number.")
        return digits

    def clean(self):
        data = super().clean()
        if data.get("lead_source") == "other" and not data.get("lead_source_other"):
            self.add_error("lead_source_other", "Tell us where this lead came from.")
        elif data.get("lead_source") != "other":
            data["lead_source_other"] = ""
        if data.get("approx_quantity") == 0:
            self.add_error("approx_quantity", "Approx quantity must be at least 1.")
        require_positive(self, "expected_value", "Expected closing value")
        return data


class MeasurementBoxForm(forms.Form):
    """Stage 1's measurements box: upload, type it out, or ask the measurement team."""

    mode = forms.ChoiceField(choices=Lead.MeasurementMode.choices, widget=forms.RadioSelect)
    file = forms.FileField(required=False, widget=forms.ClearableFileInput(attrs={"class": "form-control"}))
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "class": "form-control", "placeholder": "Type the measurements here"}),
    )
    # Travels with the request so whoever goes out can tap straight through to it.
    site_map_link = forms.URLField(
        label="Site location link",
        required=False,
        max_length=500,
        widget=forms.URLInput(attrs={"class": "form-control", "placeholder": "Paste the Google Maps link"}),
    )
    # Who is going out to the site. Left empty the whole team is told, which is
    # what happened before anyone could be picked.
    assign_to = forms.ModelChoiceField(
        label="Allocate to",
        required=False,
        queryset=User.objects.none(),
        empty_label="Anyone on the measurement team",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assign_to"].queryset = measurement_staff()
        limit_uploads(self)

    def clean(self):
        data = super().clean()
        mode = data.get("mode")
        # Measurements typed in with "Upload a file" still ticked (or a file chosen
        # with "Type them in" ticked) mean what was filled in, not what was ticked.
        if mode == Lead.MeasurementMode.FILE and not data.get("file") and data.get("notes"):
            data["mode"] = mode = Lead.MeasurementMode.TEXT
        elif mode == Lead.MeasurementMode.TEXT and not data.get("notes") and data.get("file"):
            data["mode"] = mode = Lead.MeasurementMode.FILE
        if mode == Lead.MeasurementMode.FILE and not data.get("file"):
            self.add_error("file", "Choose the measurement file to upload.")
        if mode == Lead.MeasurementMode.TEXT and not data.get("notes"):
            self.add_error("notes", "Type the measurements, or pick another option.")
        return data


class RoughMeasurementForm(forms.Form):
    """What the measurement staff submits for a requested rough measurement."""

    file = forms.FileField(required=False, widget=forms.ClearableFileInput(attrs={"class": "form-control"}))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4, "class": "form-control"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        limit_uploads(self)

    def clean(self):
        data = super().clean()
        if not data.get("file") and not data.get("notes"):
            raise forms.ValidationError("Upload the measurement file or type the measurements.")
        return data


class QuotationForm(forms.Form):
    """The quotation and its elevation report travel together to the sales executive."""

    quotation_number = forms.CharField(
        max_length=60,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter the quotation number"}),
    )
    files = MultipleFileField(label="Quotation file(s)")
    elevation = forms.FileField(
        label="Elevation report",
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
        help_text="Goes to the measurement staff for the final measurement.",
    )

    def __init__(self, *args, has_elevation=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["files"].widget.attrs.setdefault("class", "form-control")
        # A revised quotation keeps the elevation report already on file unless a
        # new one is chosen.
        self.has_elevation = has_elevation
        self.fields["elevation"].required = not has_elevation
        limit_uploads(self)

    def clean(self):
        data = super().clean()
        if not data.get("files") and "files" not in self.errors:
            self.add_error("files", "Upload the quotation.")
        if not data.get("elevation") and not self.has_elevation and "elevation" not in self.errors:
            self.add_error("elevation", "Upload the elevation report as well - both are needed.")
        return data


class ServiceComplaintForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = ServiceComplaint
        fields = ["description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3, "placeholder": "What does the customer need fixed?"})}


class ComplaintResolveForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = ServiceComplaint
        fields = ["resolution_note"]
        labels = {"resolution_note": "What was done"}


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
        limit_picker(self.fields["committed_delivery_date"], not_before_today=True)
        limit_number(self.fields["order_value"], 1)
        limit_number(self.fields["advance_received"], 0)
        limit_number(self.fields["window_count"], 1)
        limit_number(self.fields["total_sqft"], 1)

    def clean(self):
        data = super().clean()
        require_positive(self, "order_value", "Order value")
        reject_negative(self, "advance_received", "Advance received")
        require_positive(self, "window_count", "Number of windows")
        require_positive(self, "total_sqft", "Total site sq ft")
        reject_past(self, "committed_delivery_date", "Committed delivery date")
        order, advance = data.get("order_value"), data.get("advance_received")
        if order and advance and advance > order:
            self.add_error("advance_received", "Advance can't be more than the order value.")
        return data


class LostForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Lead
        fields = ["lost_reason", "lost_price_elsewhere"]
        widgets = {"lost_reason": forms.Textarea(attrs={"rows": 3})}
        labels = {"lost_reason": "Reason"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lost_reason"].required = True
        limit_number(self.fields["lost_price_elsewhere"], 1)

    def clean(self):
        data = super().clean()
        require_positive(self, "lost_price_elsewhere", "Finalised price elsewhere")
        return data


class CafFinalForm(forms.Form):
    """Stage 5 — the signed CAF and the final measurement, uploaded together."""

    caf_signed = forms.FileField(
        label="Signed CAF", required=False, widget=forms.ClearableFileInput(attrs={"class": "form-control"})
    )
    final_measurement = forms.FileField(
        label="Final measurement file", required=False, widget=forms.ClearableFileInput(attrs={"class": "form-control"})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        limit_uploads(self)

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        limit_uploads(self)


class ChecklistForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = Lead.CHECKLIST_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-check-input")


class InstallerNameInput(forms.TextInput):
    """A text box that suggests installers already on file, so one person is never two folders."""

    def render(self, name, value, attrs=None, renderer=None):
        from django.utils.html import format_html, format_html_join

        from .installation import installer_names

        attrs = {**(attrs or {}), "list": "installer-names", "autocomplete": "off"}
        box = super().render(name, value, attrs, renderer)
        options = format_html_join("", '<option value="{}">', ((known,) for known in installer_names()))
        return format_html('{}<datalist id="installer-names">{}</datalist>', box, options)


class DispatchForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Lead
        fields = ["installation_person", "installation_charge", "invoice_number", "invoice_date"]
        widgets = {
            "invoice_date": forms.DateInput(attrs={"type": "date"}),
            "installation_person": InstallerNameInput(),
        }
        labels = {"installation_person": "Installation person name", "installation_charge": "Installation charge (₹)"}
        help_texts = {"installation_charge": "Optional now — what the installer is paid for this site. It can be set later from the Installation ledger."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.required = name != "installation_charge"
        limit_picker(self.fields["invoice_date"], not_after_today=True)
        limit_number(self.fields["installation_charge"], 1)

    def clean_installation_person(self):
        from .installation import clean_name

        # Same person, same spelling, so their sites share one folder.
        return clean_name(self.cleaned_data["installation_person"])

    def clean(self):
        data = super().clean()
        reject_future(self, "invoice_date", "Invoice date")
        reject_before_order(self, "invoice_date", "Invoice date", self.instance)
        return data


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
        now = timezone.localtime()
        # After 6 pm a call booked for today is overdue the moment it is saved.
        self.fields["date"].initial = now.date() + timedelta(days=1 if now.hour >= FollowUp.CUTOFF_HOUR else 0)
        self.fields["time"].initial = time(9, 0)
        limit_picker(self.fields["date"], not_before_today=True)

    def clean(self):
        data = super().clean()
        reject_past(self, "date", "A follow-up")
        return data


class PaymentForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["paid_on", "amount", "remarks", "file"]
        widgets = {"paid_on": forms.DateInput(attrs={"type": "date"})}
        labels = {"paid_on": "Payment date"}

    def __init__(self, *args, lead=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.lead = lead
        limit_picker(self.fields["paid_on"], not_after_today=True)
        limit_number(self.fields["amount"], 1)
        limit_uploads(self)

    def clean(self):
        data = super().clean()
        require_positive(self, "amount", "Amount")
        reject_future(self, "paid_on", "Payment date")
        reject_before_order(self, "paid_on", "Payment date", self.lead)
        amount = data.get("amount")
        if self.lead is not None and amount and self.lead.balance_amount is not None:
            if amount > self.lead.balance_amount:
                self.add_error(
                    "amount",
                    f"That is more than the balance still due (₹{self.lead.balance_amount:,.2f}).",
                )
        return data


class InstallerPaymentForm(BootstrapMixin, forms.ModelForm):
    """Money paid out to the outsourced installer for one site."""

    class Meta:
        model = InstallerPayment
        fields = ["paid_on", "amount", "remarks", "file"]
        widgets = {"paid_on": forms.DateInput(attrs={"type": "date"})}
        labels = {"paid_on": "Payment date"}

    def __init__(self, *args, lead=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.lead = lead
        limit_picker(self.fields["paid_on"], not_after_today=True)
        limit_number(self.fields["amount"], 1)
        limit_uploads(self)

    def clean(self):
        data = super().clean()
        require_positive(self, "amount", "Amount")
        reject_future(self, "paid_on", "Payment date")
        balance = self.lead.installer_balance if self.lead is not None else None
        if self.lead is not None and balance is None:
            raise forms.ValidationError("Set the total payable for this site first, so the balance means something.")
        amount = data.get("amount")
        if amount and balance is not None and amount > balance:
            self.add_error("amount", f"That is more than the ₹{balance:,.2f} still owed to the installer.")
        return data


class InstallationChargeForm(BootstrapMixin, forms.ModelForm):
    """What the installer is to be paid for this site in all."""

    class Meta:
        model = Lead
        fields = ["installation_charge"]
        labels = {"installation_charge": "Total payable to the installer (₹)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["installation_charge"].required = True
        limit_number(self.fields["installation_charge"], 1)

    def clean_installation_charge(self):
        charge = self.cleaned_data["installation_charge"]
        if charge <= 0:
            raise forms.ValidationError("The total payable must be more than zero.")
        paid = self.instance.installer_paid
        if charge < paid:
            raise forms.ValidationError(f"₹{paid:,.2f} has already been paid, so the total cannot be lower than that.")
        return charge


class InvoiceChargeForm(BootstrapMixin, forms.ModelForm):
    """Transport, site charges — anything billed on top of the order value."""

    class Meta:
        model = InvoiceCharge
        fields = ["description", "amount"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].widget.attrs["placeholder"] = "e.g. Transport to site"
        limit_number(self.fields["amount"], 1)

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("A charge has to be more than zero.")
        return amount


class LedgerForm(BootstrapMixin, forms.ModelForm):
    """Lets accounts correct the headline figures on a confirmed order."""

    class Meta:
        model = Lead
        fields = ["order_value", "advance_received", "invoice_number", "invoice_date"]
        widgets = {"invoice_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["order_value"].required = True
        self.fields["advance_received"].required = True
        limit_picker(self.fields["invoice_date"], not_after_today=True)
        limit_number(self.fields["order_value"], 1)
        limit_number(self.fields["advance_received"], 0)

    def clean(self):
        data = super().clean()
        require_positive(self, "order_value", "Order value")
        reject_negative(self, "advance_received", "Advance received")
        reject_future(self, "invoice_date", "Invoice date")
        reject_before_order(self, "invoice_date", "Invoice date", self.instance)
        order, advance = data.get("order_value"), data.get("advance_received")
        if order and advance is not None and self.instance.pk:
            # What the customer is billed is the order plus anything added to the
            # invoice since, so receipts are measured against both.
            posted = sum((p.amount for p in self.instance.payments.all()), 0)
            extras = sum((c.amount for c in self.instance.invoice_charges.all()), 0)
            if advance + posted > order + extras:
                self.add_error(
                    "order_value",
                    f"Order value plus extras can't be less than what has already been received (₹{advance + posted:,.2f}).",
                )
        return data


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
        limit_picker(self.fields["due_date"], not_before_today=True)
        if user:
            self.fields["assigned_to"].initial = user

    def clean(self):
        data = super().clean()
        reject_past(self, "due_date", "Due date")
        return data


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["salesperson"].queryset = sales_executive_choices()
        self.fields["salesperson"].empty_label = "Choose a sales executive"
        limit_number(self.fields["amount"], 1)

    def validate_unique(self):
        # Saving a month that already has a target replaces it (the view
        # upserts), so the one-per-month rule must not reject the form.
        pass

    def clean(self):
        data = super().clean()
        require_positive(self, "amount", "Target")
        return data
