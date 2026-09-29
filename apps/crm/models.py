from datetime import time
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


def _total(related, field="amount"):
    """Sum a lead's payments or charges.

    Read from what the page already loaded (prefetch_related) when it did, so a
    list of a few hundred orders is not a few thousand trips to the database;
    otherwise ask the database for the one total.
    """
    rows = related.all()
    if rows._result_cache is not None:
        return sum((getattr(row, field) for row in rows), Decimal("0"))
    return rows.aggregate(total=models.Sum(field))["total"] or Decimal("0")


def plain(number):
    """A quantity as people write it: 180, 180.5 — not 180.00."""
    if number is None:
        return ""
    text = format(Decimal(number).normalize(), "f")
    return text


def credited_q(person, prefix=""):
    """The orders that count towards `person`'s sales.

    Whoever marked it won gets it when they are a sales executive; when the Super
    Admin marked it on someone's behalf (or nobody is recorded), it belongs to the
    lead's owner. So a later reassignment does not move an old win, and the Super
    Admin tidying up does not take the credit.
    """
    from apps.accounts.models import Role

    by_seller = models.Q(**{f"{prefix}won_by": person, f"{prefix}won_by__role": Role.SALESPERSON})
    on_behalf = models.Q(**{f"{prefix}assigned_to": person}) & (
        models.Q(**{f"{prefix}won_by__isnull": True}) | ~models.Q(**{f"{prefix}won_by__role": Role.SALESPERSON})
    )
    return by_seller | on_behalf


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
        FILE = "file", "Measurements uploaded by the sales executive"
        TEXT = "text", "Measurements typed by the sales executive"
        REQUESTED = "requested", "Rough measurement requested from measurement staff"

    class Fabrication(models.TextChoices):
        FUTURE = "future", "Future Production"
        UNDER = "under", "Under Production"
        READY = "ready", "Ready for Dispatch"
        DISPATCHED = "dispatched", "Dispatched"

    class Salutation(models.TextChoices):
        MR = "Mr.", "Mr."
        MRS = "Mrs.", "Mrs."
        MS = "Ms.", "Ms."
        FIRM = "M/s", "M/s (a company)"

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
    salutation = models.CharField("Title", max_length=6, choices=Salutation.choices, blank=True)
    customer_name = models.CharField(max_length=150)
    phone = models.CharField("Customer number", max_length=20)
    project_name = models.CharField(max_length=150, blank=True)
    site_location = models.CharField(max_length=255)
    # Pasted from Maps when a measurement is requested; whoever goes out taps it.
    site_map_link = models.URLField("Site location link", max_length=500, blank=True)
    lead_source = models.CharField(max_length=20, choices=LEAD_SOURCES, default="walk_in")
    lead_source_other = models.CharField("If others, please specify", max_length=120, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="leads",
        verbose_name="Sales Executive",
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
    measurement_requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    # The measurement person the sales executive picked for this site. Left
    # blank the whole team is told, as it used to be.
    measurement_assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rough_measurement_jobs",
        verbose_name="Allocate to",
    )
    measurement_done_at = models.DateTimeField(null=True, blank=True)
    measurement_done_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    # --- Stage 3: quotation ------------------------------------------------
    quotation_number = models.CharField(max_length=60, blank=True)
    quotation_uploaded_at = models.DateTimeField(null=True, blank=True)
    quotation_uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    # Set while the sales executive is waiting on a revised quotation; cleared
    # when the next one is uploaded.
    quotation_revision_pending = models.BooleanField(default=False)

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
    # Installation is outsourced and paid by the square foot: the rate is agreed,
    # and what the installer is owed is the rate times the site's total sq ft
    # (recorded when the order was won). The total is kept alongside the rate.
    installation_rate = models.DecimalField(
        "Installation rate per sq ft", max_digits=10, decimal_places=2, null=True, blank=True,
    )
    installation_charge = models.DecimalField(
        "Installation charge", max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="What the installer is paid for this site: the rate times the site's sq ft.",
    )
    invoice_number = models.CharField(max_length=60, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    dispatched_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    # --- Stage 8: installation ----------------------------------------------
    # Marked by hand once the installer has finished; handover waits on it.
    installation_completed_on = models.DateField("Installation completed on", null=True, blank=True)
    installation_completed_at = models.DateTimeField(null=True, blank=True)
    installation_completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # The last day a "not marked complete" reminder went out, so it goes once a day.
    installation_reminded_on = models.DateField(null=True, blank=True)

    # --- Stage 9: warranty & handover ---------------------------------------
    # The warranty certificate is handed to the customer; the handover
    # certificate is the one they sign and we keep.
    handover_signed_at = models.DateTimeField(null=True, blank=True)
    handover_signed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
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

    @property
    def display_name(self):
        """How the customer is addressed on paper: "Mr. Ravi Shankar"."""
        return f"{self.salutation} {self.customer_name}".strip()

    @property
    def credited_to(self):
        """Whose sales this order counts towards — the same rule as credited_q."""
        from apps.accounts.models import Role

        if self.won_by_id and self.won_by.role == Role.SALESPERSON:
            return self.won_by
        return self.assigned_to

    # --- derived values -----------------------------------------------------
    @property
    def collected(self):
        """Advance plus everything posted to the ledger since."""
        return (self.advance_received or Decimal("0")) + _total(self.payments)

    @property
    def extra_charges(self):
        """Transport and the like, added to the invoice by accounts."""
        return _total(self.invoice_charges)

    @property
    def invoice_total(self):
        """What the customer is actually billed — the order plus any extras."""
        if self.order_value is None:
            return None
        return self.order_value + self.extra_charges

    @property
    def balance_amount(self):
        if self.order_value is None:
            return None
        return self.invoice_total - self.collected

    @property
    def installer_paid(self):
        """Everything paid to the installer for this site so far."""
        return _total(self.installer_payments)

    @property
    def installer_extras(self):
        """Anything added to what the installer is owed on top of the per-sq-ft charge."""
        return _total(self.installer_charges)

    @property
    def installer_payable(self):
        """The charge plus anything added since, or None while there is neither."""
        extras = self.installer_extras
        if self.installation_charge is None and not extras:
            return None
        return (self.installation_charge or Decimal("0")) + extras

    @property
    def installer_balance(self):
        """Still owed to the installer, or None until something is payable."""
        payable = self.installer_payable
        if payable is None:
            return None
        return payable - self.installer_paid

    @property
    def site_name(self):
        """What the site is called on the installer's list."""
        return self.project_name or self.customer_name

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
    def current_quotation_files(self):
        """The latest quotation's files — a revision's, once there is one — never an earlier price."""
        return self.quotation_files.filter(replaced_at__isnull=True)

    @property
    def earlier_quotation_files(self):
        """Quotations a revision has replaced, kept for the record."""
        return self.quotation_files.filter(replaced_at__isnull=False)

    @property
    def current_elevation(self):
        """The elevation report in use — a revision may keep the one already on file."""
        return self.uploads.filter(kind="elevation", replaced_at__isnull=True).first()

    @property
    def earlier_elevations(self):
        return self.uploads.filter(kind="elevation", replaced_at__isnull=False)

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
        return self.uploads.filter(kind__in=["handover_signed", "warranty_signed"])

    # The order a finished job's paperwork is read in.
    DOCUMENT_ORDER = [
        "quotation",
        "caf_signed",
        "final_measurement",
        "production_sheet",
        "handover_signed",
        "warranty_signed",
    ]

    @property
    def site_documents(self):
        """Every stored document for the job, in the order it was produced."""
        by_kind = {}
        for upload in self.uploads.all():
            by_kind.setdefault(upload.kind, []).append(upload)
        return [upload for kind in self.DOCUMENT_ORDER for upload in by_kind.get(kind, [])]

    @property
    def overdue_days(self):
        """Days since the invoice went out, for anything still unpaid."""
        if not self.is_outstanding or not self.invoice_date:
            return 0
        return max(0, (timezone.localdate() - self.invoice_date).days)

    @property
    def ready_for_production(self):
        """Approved and waiting on the floor to pick it up."""
        return self.production_approved_at is not None and self.fabrication_column == self.Fabrication.FUTURE

    @property
    def project_label(self):
        """What the CAF prints against "Project Name / Site Location"."""
        if self.project_name:
            return f"{self.project_name}, {self.site_location}"
        return self.site_location

    @property
    def open_followup(self):
        """Only one follow-up runs at a time, so there is at most one of these."""
        return self.followups.filter(done=False).order_by("date", "time").first()

    @property
    def followup_history(self):
        """The ones already closed out, most recent first."""
        return self.followups.filter(done=True).order_by("-date", "-time")


class LeadFile(models.Model):
    class Kind(models.TextChoices):
        ROUGH_MEASUREMENT = "rough_measurement", "Rough Measurement"
        QUOTATION = "quotation", "Quotation"
        CAF_SIGNED = "caf_signed", "Signed CAF"
        FINAL_MEASUREMENT = "final_measurement", "Final Measurement"
        PRODUCTION_SHEET = "production_sheet", "Production Sheet"
        ELEVATION = "elevation", "Elevation Report"
        HANDOVER_SIGNED = "handover_signed", "Signed Handover Certificate"
        # Jobs finished before the certificate was renamed still carry this kind.
        WARRANTY_SIGNED = "warranty_signed", "Signed Warranty Certificate"

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="uploads")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    file = models.FileField(upload_to="leads/%Y/%m/")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    # Set when a revision brings a newer one of the same kind; kept for the record.
    replaced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.lead.lead_number}"

    @property
    def filename(self):
        return self.file.name.rsplit("/", 1)[-1]

    @property
    def download_url(self):
        """Handed over as a download, so it opens in the phone's own PDF app, not inside ours."""
        return reverse("crm:lead_file", args=[self.pk])


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
    # Closed out because a newer follow-up replaced it, rather than by being worked.
    superseded = models.BooleanField(default=False)
    # Closed out because the lead was won or lost, rather than by being worked.
    closed_with_lead = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "time"]

    def __str__(self):
        return f"Follow-up {self.date} — {self.lead.customer_name}"

    @property
    def outcome(self):
        """What the history line should say — a rescheduled one was never worked."""
        if not self.done:
            return "Open"
        if self.closed_with_lead:
            return "Closed with the lead"
        return "Rescheduled" if self.superseded else "Completed"

    @classmethod
    def overdue_q(cls, now=None):
        """The same rule as is_overdue, for a query: an earlier day, or today after 6 pm."""
        now = now or timezone.localtime()
        late = models.Q(date__lt=now.date())
        if now.hour >= cls.CUTOFF_HOUR:
            late |= models.Q(date=now.date())
        return late & models.Q(done=False)

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


class QuotationRevision(models.Model):
    """A quotation the sales executive has asked to have redone."""

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="quotation_revisions")
    note = models.TextField()
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    requested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["requested_at"]

    def __str__(self):
        return f"Quotation revision for {self.lead.lead_number}"


class LeadAssignment(models.Model):
    """Who a lead moved from, to, and when — so old work keeps its own name."""

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="assignments")
    from_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    to_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["changed_at"]

    def __str__(self):
        return f"{self.lead.lead_number}: {self.from_user} -> {self.to_user}"


class ProductionRevision(models.Model):
    """A production sheet sent back for changes. Kept so the timeline has them all."""

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="production_revisions")
    note = models.TextField()
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    requested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["requested_at"]

    def __str__(self):
        return f"Revision for {self.lead.lead_number}"


class SalesTarget(models.Model):
    salesperson = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="targets", verbose_name="Sales Executive"
    )
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
    def won_leads(self):
        """Every order credited to this sales executive inside the month (see credited_q)."""
        return Lead.objects.filter(
            credited_q(self.salesperson),
            status=Lead.Status.WON,
            won_at__year=self.month.year,
            won_at__month=self.month.month,
        )

    @property
    def achieved(self):
        """Finalised value of everything this sales executive won inside the month."""
        return self.won_leads.aggregate(t=models.Sum("order_value"))["t"] or Decimal("0")

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


class InvoiceCharge(models.Model):
    """Something added to the invoice after the order was priced.

    Transport the customer asked us to bear, a site charge, anything the
    accounts team needs on the bill that was not in the order value.
    """

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="invoice_charges")
    description = models.CharField("What the charge is for", max_length=180)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["added_at", "id"]

    def __str__(self):
        return f"{self.description} — {self.amount}"


class Payment(models.Model):
    """A line in a lead's payment ledger, posted by the accounts team."""

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="payments")
    paid_on = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    remarks = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["paid_on", "id"]

    def __str__(self):
        return f"{self.lead.customer_name} — {self.amount}"


class InstallerPayment(models.Model):
    """Money paid to the outsourced installer for one site."""

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="installer_payments")
    paid_on = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    remarks = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["paid_on", "id"]

    def __str__(self):
        return f"{self.lead.installation_person} — {self.amount}"


class InstallerCharge(models.Model):
    """Extra money owed to the installer for one site, on top of the per-sq-ft charge.

    Added under "Add to the payable" on the site's ledger: a second visit, extra
    scaffolding, carrying glass up to a high floor.
    """

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="installer_charges")
    added_on = models.DateField("Date", default=timezone.localdate)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField("What it is for", max_length=180)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["added_on", "id"]

    def __str__(self):
        return f"{self.lead.installation_person} + {self.amount} ({self.description})"


class PaymentReceipt(models.Model):
    """A proof or receipt for a customer payment. A payment can carry several."""

    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="receipts")
    file = models.FileField("Proof / receipt", upload_to="payments/%Y/%m/")

    class Meta:
        ordering = ["id"]

    @property
    def filename(self):
        return self.file.name.rsplit("/", 1)[-1]

    @property
    def download_url(self):
        return reverse("crm:payment_receipt", args=[self.pk])


class InstallerReceipt(models.Model):
    """A proof or receipt for a payment to an installer. A payment can carry several."""

    payment = models.ForeignKey(InstallerPayment, on_delete=models.CASCADE, related_name="receipts")
    file = models.FileField("Proof / receipt", upload_to="installers/%Y/%m/")

    class Meta:
        ordering = ["id"]

    @property
    def filename(self):
        return self.file.name.rsplit("/", 1)[-1]

    @property
    def download_url(self):
        return reverse("crm:installer_receipt", args=[self.pk])


class MarketingSpend(models.Model):
    """What was spent to bring in leads from one source in one month.

    Entered by the Super Admin on the monthly summary. Without it the report can
    say which source brings the most orders; with it, it can say which is worth
    the money.
    """

    month = models.DateField(help_text="The 1st of the month.")
    source = models.CharField(max_length=20, choices=Lead.LEAD_SOURCES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["-month", "source"]
        unique_together = [("month", "source")]

    def __str__(self):
        return f"{self.get_source_display()} {self.month:%b %Y}: {self.amount}"

    def save(self, *args, **kwargs):
        self.month = self.month.replace(day=1)
        super().save(*args, **kwargs)


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
    # The person who handed it out has seen it completed and cleared it from
    # their "Assigned by me" list. It stays on the assignee's own list as done.
    cleared_by_assigner_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["done", "due_date", "-created_at"]

    def __str__(self):
        return self.title

    @classmethod
    def handed_out_by(cls, user):
        """What `user` assigned to other people and has not cleared.

        Completed ones first, newest first, since they are the news and wait to be
        cleared; then the open ones, soonest due first.
        """
        return (
            cls.objects.filter(assigned_by=user, cleared_by_assigner_at__isnull=True)
            .exclude(assigned_to=user)
            .select_related("assigned_to")
            .order_by("-done", "-done_at", "due_date", "-created_at")
        )

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
    # What the update is waiting for ("rough", "todo:12", "password:5"), so it can be
    # cleared for everyone it went to the moment that is done. See crm/updates.py.
    topic = models.CharField(max_length=40, blank=True, db_index=True)
    # Where it opens, when that is not the lead's own page.
    link = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.message

    @property
    def url(self):
        """Where tapping the update takes you, or "" when there is nowhere better to go."""
        if self.link:
            return self.link
        if self.lead_id:
            return self.lead.get_absolute_url()
        return ""
