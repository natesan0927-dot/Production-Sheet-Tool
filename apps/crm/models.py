from datetime import time
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Lead(models.Model):
    """A lead *is* a customer (per the spec, they are the same record).

    Every stage of the journey lives on this one row so the whole process is
    readable in one place; uploaded documents hang off it via LeadFile.
    """

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        WON = "won", "Won"
        LOST = "lost", "Lost"

    class MeasurementMode(models.TextChoices):
        FILE = "file", "Measurements uploaded by salesperson"
        TEXT = "text", "Measurements typed by salesperson"
        REQUESTED = "requested", "Rough measurement requested from measurement staff"

    class Fabrication(models.TextChoices):
        FUTURE = "future", "Future Production"
        UNDER = "under", "Under Production"
        READY = "ready", "Ready for Dispatch"
        DISPATCHED = "dispatched", "Dispatched"

    LEAD_SOURCES = [
        ("walk_in", "Walk-in"),
        ("reference", "Reference"),
        ("website", "Website"),
        ("meta", "Meta"),
        ("mccoymart", "McCoyMart"),
        ("indiamart", "IndiaMART"),
        ("tradeindia", "TradeIndia"),
        ("justdial", "JustDial"),
        ("google", "Google"),
        ("bni", "BNI"),
        ("other", "Others"),
    ]

    SITE_STAGES = [
        ("not_started", "Not Started"),
        ("foundation", "Foundation"),
        ("brickwork", "Brick Work"),
        ("plastering", "Plastering"),
        ("ready", "Ready for Installation"),
    ]

    # --- Stage 1: lead created -------------------------------------------
    lead_number = models.CharField(max_length=20, unique=True, editable=False)
    customer_name = models.CharField(max_length=150)
    phone = models.CharField("Customer number", max_length=20)
    project_name = models.CharField(max_length=150, blank=True)
    site_location = models.CharField(max_length=255)
    lead_source = models.CharField(max_length=20, choices=LEAD_SOURCES, default="walk_in")
    lead_source_other = models.CharField("If others, please specify", max_length=120, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="leads",
        verbose_name="Assigned salesperson",
    )
    approx_quantity = models.PositiveIntegerField("Approx quantity (nos.)", null=True, blank=True)
    expected_value = models.DecimalField("Expected closing value", max_digits=12, decimal_places=2, null=True, blank=True)
    site_stage = models.CharField(max_length=20, choices=SITE_STAGES, default="not_started")
    remarks = models.TextField(blank=True)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --- Stage 2: rough measurement ---------------------------------------
    measurement_mode = models.CharField(max_length=12, choices=MeasurementMode.choices, blank=True)
    measurement_notes = models.TextField(blank=True)
    measurement_requested_at = models.DateTimeField(null=True, blank=True)
    measurement_done_at = models.DateTimeField(null=True, blank=True)
    measurement_done_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    # --- Stage 3: quotation ------------------------------------------------
    quotation_number = models.CharField(max_length=60, blank=True)
    quotation_uploaded_at = models.DateTimeField(null=True, blank=True)
    quotation_uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    # --- Stage 4: won / lost ------------------------------------------------
    order_value = models.DecimalField("Order finalized value", max_digits=12, decimal_places=2, null=True, blank=True)
    advance_received = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    committed_delivery_date = models.DateField(null=True, blank=True)
    won_remarks = models.TextField(blank=True)
    won_at = models.DateTimeField(null=True, blank=True)
    won_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    lost_reason = models.TextField(blank=True)
    lost_price_elsewhere = models.DecimalField("Finalised price elsewhere", max_digits=12, decimal_places=2, null=True, blank=True)
    lost_at = models.DateTimeField(null=True, blank=True)
    lost_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    # --- Stage 5: CAF & final measurement -----------------------------------
    caf_signed_at = models.DateTimeField(null=True, blank=True)
    final_measurement_at = models.DateTimeField(null=True, blank=True)
    caf_final_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    # --- Stage 6: production sheet ------------------------------------------
    production_sheet_at = models.DateTimeField(null=True, blank=True)
    production_sheet_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    production_approved_at = models.DateTimeField(null=True, blank=True)
    production_approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    production_revision_note = models.TextField(blank=True)
    production_revision_at = models.DateTimeField(null=True, blank=True)

    # --- Stage 7: site fabrication status -----------------------------------
    fabrication_column = models.CharField(max_length=12, choices=Fabrication.choices, default=Fabrication.FUTURE)
    window_count = models.PositiveIntegerField("Number of windows", null=True, blank=True)
    total_sqft = models.DecimalField("Total site sq ft", max_digits=10, decimal_places=2, null=True, blank=True)
    fabrication_value = models.DecimalField("Order value", max_digits=12, decimal_places=2, null=True, blank=True)

    chk_cutting = models.BooleanField("Cutting", default=False)
    chk_reinforcement = models.BooleanField("Reinforcement", default=False)
    chk_welding = models.BooleanField("Welding", default=False)
    chk_beading = models.BooleanField("Beading", default=False)
    chk_cnc = models.BooleanField("CNC", default=False)
    chk_assembly = models.BooleanField("Assembly", default=False)
    chk_glass_cutting = models.BooleanField("Glass Cutting", default=False)
    chk_glass_installation = models.BooleanField("Glass Installation", default=False)

    installation_person = models.CharField(max_length=150, blank=True)
    invoice_number = models.CharField(max_length=60, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    dispatched_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    # --- Stage 8: warranty & handover ---------------------------------------
    # The warranty certificate is handed to the customer; the handover
    # certificate is the one they sign and we keep.
    handover_signed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    CHECKLIST_FIELDS = [
        "chk_cutting",
        "chk_reinforcement",
        "chk_welding",
        "chk_beading",
        "chk_cnc",
        "chk_assembly",
        "chk_glass_cutting",
        "chk_glass_installation",
    ]

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.lead_number} — {self.customer_name}"

    def save(self, *args, **kwargs):
        if not self.lead_number:
            last = Lead.objects.order_by("-id").first()
            nxt = (last.id + 1) if last else 1
            self.lead_number = f"TW-{nxt:04d}"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("crm:lead_detail", args=[self.pk])

    # --- derived values -----------------------------------------------------
    @property
    def collected(self):
        """Advance plus everything posted to the ledger since."""
        posted = self.payments.aggregate(total=models.Sum("amount"))["total"] or Decimal("0")
        return (self.advance_received or Decimal("0")) + posted

    @property
    def balance_amount(self):
        if self.order_value is None:
            return None
        return self.order_value - self.collected

    @property
    def is_outstanding(self):
        """Money only counts as outstanding once the customer has been invoiced."""
        return bool(self.invoice_date) and (self.balance_amount or Decimal("0")) > 0

    @property
    def checklist(self):
        return [(self._meta.get_field(f).verbose_name, getattr(self, f), f) for f in self.CHECKLIST_FIELDS]

    @property
    def checklist_done_count(self):
        return sum(1 for f in self.CHECKLIST_FIELDS if getattr(self, f))

    @property
    def is_completed(self):
        return self.completed_at is not None

    @property
    def rough_measurement_files(self):
        return self.uploads.filter(kind="rough_measurement")

    @property
    def quotation_files(self):
        return self.uploads.filter(kind="quotation")

    @property
    def measurement_documents(self):
        """The signed CAF and the final measurement, which travel together."""
        return self.uploads.filter(kind__in=["caf_signed", "final_measurement"])

    @property
    def production_sheet_files(self):
        return self.uploads.filter(kind="production_sheet")

    @property
    def elevation_files(self):
        return self.uploads.filter(kind="elevation")

    @property
    def handover_files(self):
        return self.uploads.filter(kind="handover_signed")

    @property
    def project_label(self):
        """What the CAF prints against "Project Name / Site Location"."""
        if self.project_name:
            return f"{self.project_name}, {self.site_location}"
        return self.site_location

    @property
    def next_followup(self):
        return self.followups.filter(done=False).order_by("date", "time").first()


class LeadFile(models.Model):
    class Kind(models.TextChoices):
        ROUGH_MEASUREMENT = "rough_measurement", "Rough Measurement"
        QUOTATION = "quotation", "Quotation"
        CAF_SIGNED = "caf_signed", "Signed CAF"
        FINAL_MEASUREMENT = "final_measurement", "Final Measurement"
        PRODUCTION_SHEET = "production_sheet", "Production Sheet"
        ELEVATION = "elevation", "Elevation Report"
        HANDOVER_SIGNED = "handover_signed", "Signed Handover Certificate"

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="uploads")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    file = models.FileField(upload_to="leads/%Y/%m/")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.lead.lead_number}"

    @property
    def filename(self):
        return self.file.name.rsplit("/", 1)[-1]


def nine_am():
    return time(9, 0)


class FollowUp(models.Model):
    # A follow-up left untouched by the end of the working day is overdue.
    CUTOFF_HOUR = 18

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="followups")
    date = models.DateField(default=timezone.localdate)
    time = models.TimeField(default=nine_am)
    note = models.CharField(max_length=255, blank=True)
    done = models.BooleanField(default=False)
    done_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "time"]

    def __str__(self):
        return f"Follow-up {self.date} — {self.lead.customer_name}"

    @property
    def is_overdue(self):
        if self.done:
            return False
        now = timezone.localtime()
        if self.date < now.date():
            return True
        return self.date == now.date() and now.hour >= self.CUTOFF_HOUR

    @property
    def can_be_completed(self):
        """Closed leads have their follow-ups closed out with them."""
        return self.lead.status == Lead.Status.OPEN


class SalesTarget(models.Model):
    salesperson = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="targets")
    month = models.DateField(help_text="Any date inside the target month; stored as the 1st.")
    amount = models.DecimalField("Target for the month", max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["-month"]
        unique_together = [("salesperson", "month")]

    def __str__(self):
        return f"{self.salesperson} — {self.month:%b %Y}"

    def save(self, *args, **kwargs):
        self.month = self.month.replace(day=1)
        super().save(*args, **kwargs)

    @property
    def achieved(self):
        """Finalised value of everything this salesperson won inside the month."""
        total = Lead.objects.filter(
            assigned_to=self.salesperson,
            status=Lead.Status.WON,
            won_at__year=self.month.year,
            won_at__month=self.month.month,
        ).aggregate(t=models.Sum("order_value"))["t"]
        return total or Decimal("0")

    @property
    def pending(self):
        return max(self.amount - self.achieved, Decimal("0"))

    @property
    def percent(self):
        if not self.amount:
            return 0
        return min(int(self.achieved / self.amount * 100), 100)


class ServiceComplaint(models.Model):
    """Raised against a finished project when the customer needs a technician."""

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="complaints")
    description = models.TextField("What needs fixing")
    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    raised_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    resolution_note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["resolved_at", "-raised_at"]

    def __str__(self):
        return f"Complaint — {self.lead.customer_name}"

    @property
    def is_open(self):
        return self.resolved_at is None


class Payment(models.Model):
    """A line in a lead's payment ledger, posted by the accounts team."""

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="payments")
    paid_on = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    remarks = models.CharField(max_length=255, blank=True)
    file = models.FileField("Proof / receipt", upload_to="payments/%Y/%m/", blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["paid_on", "id"]

    def __str__(self):
        return f"{self.lead.customer_name} — {self.amount}"


class Task(models.Model):
    """A to-do. Anyone can assign one to anyone; it lands on that person's list."""

    title = models.CharField(max_length=200)
    details = models.TextField(blank=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="todos")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="assigned_todos"
    )
    due_date = models.DateField(null=True, blank=True)
    done = models.BooleanField(default=False)
    done_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["done", "due_date", "-created_at"]

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        return not self.done and self.due_date is not None and self.due_date < timezone.localdate()

    @property
    def is_self_assigned(self):
        return self.assigned_by_id == self.assigned_to_id


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    # A to-do notification has no lead behind it.
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="notifications", null=True, blank=True)
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    read = models.BooleanField(default=False)
    # Ticked off from "Updates for the day" — separate from read, which the bell sets.
    dismissed = models.BooleanField(default=False)
    # Shown once as a pop-up; it stays in the notifications list either way.
    popped = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.message
