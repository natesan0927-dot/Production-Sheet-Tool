from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from simple_history.models import HistoricalRecords

from apps.core.models import PaymentTermTemplate


class Quotation(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("sent", "Sent"),
        ("negotiation", "Under Negotiation"),
        ("won", "Won"),
        ("lost", "Lost"),
        ("superseded", "Superseded by Revision"),
    ]

    root_number = models.CharField(max_length=20)
    version = models.PositiveSmallIntegerField(default=1)
    lead = models.ForeignKey("crm.Lead", on_delete=models.CASCADE, related_name="quotations")
    customer = models.ForeignKey("crm.Customer", on_delete=models.CASCADE, related_name="quotations")
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="draft")

    payment_terms = models.ForeignKey(PaymentTermTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    delivery_period = models.CharField(max_length=100, blank=True)
    warranty_text = models.TextField(blank=True)
    terms_text = models.TextField(blank=True)

    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=18)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    prepared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="quotations_prepared"
    )
    revised_from = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="revisions")
    revision_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.quotation_number

    @property
    def quotation_number(self):
        return f"{self.root_number}-V{self.version}"

    def save(self, *args, **kwargs):
        if not self.root_number:
            from apps.core.numbering import get_next_number

            self.root_number = get_next_number("quotation")
        super().save(*args, **kwargs)

    def recalculate_totals(self, save=True):
        subtotal = sum((item.amount for item in self.items.all()), Decimal("0"))
        self.subtotal = subtotal
        taxable = subtotal - self.discount
        self.tax_amount = (taxable * self.tax_percent / Decimal("100")).quantize(Decimal("0.01"))
        self.total_value = taxable + self.tax_amount
        if save:
            self.save(update_fields=["subtotal", "tax_amount", "total_value"])

    def get_absolute_url(self):
        return reverse("sales:quotation_detail", args=[self.pk])


class QuotationItem(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=200)
    dimensions = models.CharField(max_length=100, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0, editable=False)
    glass = models.CharField(max_length=150, blank=True)
    hardware = models.CharField(max_length=150, blank=True)
    accessories = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.description} x{self.quantity}"

    def save(self, *args, **kwargs):
        self.amount = (self.unit_rate or 0) * (self.quantity or 0)
        super().save(*args, **kwargs)


class SalesTarget(models.Model):
    salesperson = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="sales_targets"
    )
    team_name = models.CharField(max_length=100, blank=True)
    branch = models.CharField(max_length=100, blank=True)
    product_category = models.CharField(max_length=100, blank=True)
    year = models.PositiveIntegerField()
    month = models.PositiveSmallIntegerField()
    target_amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["-year", "-month"]
        unique_together = ("salesperson", "team_name", "branch", "product_category", "year", "month")

    def __str__(self):
        return f"{self.salesperson or self.team_name or self.branch} {self.month}/{self.year}"

    def achieved_amount(self):
        qs = Order.objects.filter(confirmed_at__year=self.year, confirmed_at__month=self.month)
        if self.salesperson_id:
            qs = qs.filter(salesperson=self.salesperson)
        return qs.aggregate(total=models.Sum("final_value"))["total"] or Decimal("0")

    def pending_amount(self):
        return self.target_amount - self.achieved_amount()

    def achievement_percent(self):
        if not self.target_amount:
            return 0
        return round((self.achieved_amount() / self.target_amount) * 100, 1)


class Order(models.Model):
    STATUS_CHOICES = [
        ("confirmed", "Confirmed"),
        ("caf_generated", "Customer Acquisition Form Generated"),
        ("final_measurement", "Final Measurement"),
        ("production", "In Production"),
        ("qc", "Quality Check"),
        ("dispatch", "Dispatch"),
        ("installation", "Installation"),
        ("handover", "Handed Over"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    order_number = models.CharField(max_length=20, unique=True, blank=True)
    lead = models.OneToOneField("crm.Lead", on_delete=models.CASCADE, related_name="order")
    customer = models.ForeignKey("crm.Customer", on_delete=models.CASCADE, related_name="orders")
    quotation = models.ForeignKey(Quotation, on_delete=models.PROTECT, related_name="orders")
    confirmed_quotation_version = models.PositiveSmallIntegerField()

    original_quotation_value = models.DecimalField(max_digits=14, decimal_places=2)
    final_order_value = models.DecimalField(max_digits=14, decimal_places=2)
    discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    final_value = models.DecimalField(max_digits=14, decimal_places=2)

    payment_terms = models.ForeignKey(PaymentTermTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    advance_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    balance_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    expected_delivery_date = models.DateField(null=True, blank=True)
    expected_installation_date = models.DateField(null=True, blank=True)
    special_instructions = models.TextField(blank=True)

    salesperson = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders_won")
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="confirmed")
    confirmed_at = models.DateTimeField(auto_now_add=True)

    is_invoiced = models.BooleanField(default=False)
    invoiced_at = models.DateTimeField(null=True, blank=True)
    invoiced_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["-confirmed_at"]

    def __str__(self):
        return self.order_number

    def save(self, *args, **kwargs):
        if not self.order_number:
            from apps.core.numbering import get_next_number

            self.order_number = get_next_number("order")
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("sales:order_detail", args=[self.pk])

    def total_paid(self):
        return self.payments.aggregate(total=models.Sum("amount"))["total"] or Decimal("0")

    def due_amount(self):
        return self.final_value - self.total_paid()

    def payment_status(self):
        paid = self.total_paid()
        if paid <= 0:
            return "Not Paid"
        if paid < self.final_value:
            return "Partially Paid"
        return "Paid"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=200)
    dimensions = models.CharField(max_length=100, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    glass = models.CharField(max_length=150, blank=True)
    hardware = models.CharField(max_length=150, blank=True)
    accessories = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.description} x{self.quantity}"


class Payment(models.Model):
    MODE_CHOICES = [
        ("cash", "Cash"), ("cheque", "Cheque"), ("bank_transfer", "Bank Transfer"),
        ("upi", "UPI"), ("card", "Card"), ("other", "Other"),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default="bank_transfer")
    date = models.DateField()
    reference = models.CharField(max_length=100, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.order.order_number} - {self.amount}"


class CustomerAcquisitionForm(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="acquisition_form")
    version = models.PositiveSmallIntegerField(default=1)
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    pdf_file = models.FileField(upload_to="caf/%Y/%m/", blank=True, null=True)

    # The customer's physically signed copy -- production cannot be approved
    # until this is uploaded (see apps.production.views.sheet_approve).
    is_signed = models.BooleanField(default=False)
    signed_pdf_file = models.FileField(upload_to="caf/signed/%Y/%m/", blank=True, null=True)
    signed_uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    signed_uploaded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self):
        return f"CAF - {self.order.order_number} v{self.version}"
