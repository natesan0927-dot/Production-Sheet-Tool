from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse


class SingletonModel(models.Model):
    """Base class for models that must only ever have one row (pk=1)."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class CompanyProfile(SingletonModel):
    """Company / brand information. Configurable in Admin Settings, never hard-coded."""

    name = models.CharField(max_length=200, default="Titans Windows")
    tagline = models.CharField(max_length=200, blank=True, default="uPVC Windows & Doors Manufacturing")
    logo = models.ImageField(upload_to="company/", blank=True, null=True)
    address = models.TextField(blank=True, default="Chennai, Tamil Nadu, India")
    city = models.CharField(max_length=100, blank=True, default="Chennai")
    state = models.CharField(max_length=100, blank=True, default="Tamil Nadu")
    pincode = models.CharField(max_length=10, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    website = models.CharField(max_length=200, blank=True)
    gst_number = models.CharField(max_length=20, blank=True)
    default_tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=18)
    default_quotation_terms = models.TextField(blank=True)
    default_warranty_years = models.PositiveSmallIntegerField(default=10)
    default_warranty_terms = models.TextField(
        blank=True,
        default="10 years warranty on uPVC profile, 1 year warranty on hardware and accessories.",
    )

    class Meta:
        verbose_name = "Company Profile"
        verbose_name_plural = "Company Profile"

    def __str__(self):
        return self.name


class NumberSequence(models.Model):
    """
    Configurable document numbering. Produces values such as LEAD-2026-00001,
    QUO-2026-00045, ORD-2026-00001 without ever hard-coding a format.
    """

    doc_type = models.CharField(max_length=30, unique=True)
    prefix = models.CharField(max_length=15)
    year = models.PositiveIntegerField()
    last_number = models.PositiveIntegerField(default=0)
    padding = models.PositiveSmallIntegerField(default=5)

    class Meta:
        verbose_name = "Numbering Format"
        ordering = ["doc_type"]

    def __str__(self):
        return f"{self.doc_type}: {self.prefix}-{self.year}-{'0' * self.padding}"


class LeadSource(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class LeadStatus(models.Model):
    """Configurable lead pipeline stage (New, Contacted, Won, Lost, ...)."""

    name = models.CharField(max_length=50, unique=True)
    sequence = models.PositiveSmallIntegerField(default=0)
    is_won = models.BooleanField(default=False)
    is_lost = models.BooleanField(default=False)
    is_default = models.BooleanField(default=False)
    color = models.CharField(max_length=20, default="secondary", help_text="Bootstrap color, e.g. primary, success")

    class Meta:
        verbose_name_plural = "Lead statuses"
        ordering = ["sequence", "name"]

    def __str__(self):
        return self.name


class LostReason(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Competitor(models.Model):
    name = models.CharField(max_length=150, unique=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProfileSeries(models.Model):
    brand = models.CharField(max_length=100, blank=True)
    series = models.CharField(max_length=100)
    colour = models.CharField(max_length=50, blank=True)
    specification = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Profile series"
        ordering = ["brand", "series"]

    def __str__(self):
        label = self.series
        if self.brand:
            label = f"{self.brand} - {label}"
        if self.colour:
            label = f"{label} ({self.colour})"
        return label


class GlassType(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class HardwareType(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class AccessoryType(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class PaymentTermTemplate(models.Model):
    """
    Configurable payment schedule, e.g. 50% advance / 40% before dispatch / 10%
    after installation. Admin can add/edit/reorder steps.
    """

    name = models.CharField(max_length=100, unique=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class PaymentTermStep(models.Model):
    template = models.ForeignKey(PaymentTermTemplate, on_delete=models.CASCADE, related_name="steps")
    label = models.CharField(max_length=100)
    percent = models.DecimalField(max_digits=5, decimal_places=2)
    trigger = models.CharField(max_length=100, blank=True, help_text="e.g. On order confirmation, Before dispatch")
    sequence = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["template", "sequence"]

    def __str__(self):
        return f"{self.label} ({self.percent}%)"


class ProductionStageTemplate(models.Model):
    name = models.CharField(max_length=100, unique=True)
    sequence = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sequence"]

    def __str__(self):
        return self.name


class QCChecklistItem(models.Model):
    name = models.CharField(max_length=150, unique=True)
    sequence = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sequence"]

    def __str__(self):
        return self.name


class InstallationChecklistItem(models.Model):
    name = models.CharField(max_length=150, unique=True)
    sequence = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sequence"]

    def __str__(self):
        return self.name


class ServiceCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Service categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class DocumentTemplate(models.Model):
    """
    Admin-editable HTML template used to render generated PDFs (Customer
    Acquisition Form, quotation, handover certificate, warranty certificate...).
    Body may use Django template placeholders, e.g. {{ customer_name }}.
    """

    CODE_CHOICES = [
        ("customer_acquisition_form", "Customer Acquisition Form"),
        ("quotation", "Quotation"),
        ("order_confirmation", "Order Confirmation"),
        ("handover_certificate", "Handover Certificate"),
        ("warranty_certificate", "Warranty Certificate"),
    ]

    code = models.CharField(max_length=50, choices=CODE_CHOICES, unique=True)
    name = models.CharField(max_length=150)
    html_body = models.TextField(help_text="Django template syntax. Available fields depend on the document type.")
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Document(models.Model):
    """
    Every generated or uploaded document (quotation PDF, CAF, measurement
    drawing, handover certificate, exported Excel...) linked to whatever
    business record it belongs to, with version history.
    """

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    related_object = GenericForeignKey("content_type", "object_id")

    doc_type = models.CharField(max_length=50)
    file = models.FileField(upload_to="documents/%Y/%m/")
    version = models.PositiveSmallIntegerField(default=1)
    description = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    auto_generated = models.BooleanField(default=False)

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self):
        return f"{self.doc_type} v{self.version}"


class Attachment(models.Model):
    """Generic photo/drawing/signature upload attached to any record."""

    CATEGORY_CHOICES = [
        ("site_photo", "Site Photo"),
        ("drawing", "Drawing / Sketch"),
        ("measurement_sheet", "Measurement Sheet (photo/PDF)"),
        ("before", "Before Photo"),
        ("during", "During Photo"),
        ("completion", "Completion Photo"),
        ("signature", "Signature"),
        ("other", "Other"),
    ]

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    related_object = GenericForeignKey("content_type", "object_id")

    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="other")
    file = models.FileField(upload_to="attachments/%Y/%m/")
    caption = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self):
        return f"{self.get_category_display()} - {self.uploaded_at:%Y-%m-%d}"


class EmployeeTask(models.Model):
    """
    Generic ad-hoc task (section 30) that can also be used to aggregate a
    "My Tasks" view across every department, on top of the domain-specific
    task objects (MeasurementRequest, ProductionTask, Installation, ...)
    which already carry their own status/assignee.
    """

    PRIORITY_CHOICES = [("low", "Low"), ("normal", "Normal"), ("high", "High"), ("urgent", "Urgent")]
    STATUS_CHOICES = [("pending", "Pending"), ("in_progress", "In Progress"), ("completed", "Completed"), ("overdue", "Overdue")]

    task_id = models.CharField(max_length=20, unique=True, blank=True)
    department = models.CharField(max_length=100, blank=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tasks")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    title = models.CharField(max_length=200)
    created_date = models.DateTimeField(auto_now_add=True)
    due_date = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="normal")
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="pending")
    remarks = models.TextField(blank=True)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    related_object = GenericForeignKey("content_type", "object_id")

    class Meta:
        ordering = ["due_date", "-priority"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.task_id:
            from apps.core.numbering import get_next_number

            self.task_id = get_next_number("task")
        super().save(*args, **kwargs)


class Notification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    verb = models.CharField(max_length=255)
    message = models.CharField(max_length=500, blank=True)
    url = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    related_object = GenericForeignKey("content_type", "object_id")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.verb

    def get_absolute_url(self):
        return self.url or "#"
