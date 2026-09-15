from django.conf import settings
from django.db import models
from django.urls import reverse
from simple_history.models import HistoricalRecords


class Warranty(models.Model):
    order = models.OneToOneField("sales.Order", on_delete=models.CASCADE, related_name="warranty")
    certificate_number = models.CharField(max_length=20, unique=True, blank=True)
    product_summary = models.TextField(blank=True)
    warranty_start_date = models.DateField()
    warranty_end_date = models.DateField()
    warranty_terms = models.TextField(blank=True)
    certificate_pdf = models.FileField(upload_to="warranty/%Y/%m/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.certificate_number

    def save(self, *args, **kwargs):
        if not self.certificate_number:
            from apps.core.numbering import get_next_number

            self.certificate_number = get_next_number("warranty")
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("aftersales:warranty_detail", args=[self.pk])

    def is_active(self):
        from django.utils import timezone

        return self.warranty_start_date <= timezone.now().date() <= self.warranty_end_date


class ServiceComplaint(models.Model):
    STATUS_CHOICES = [
        ("new", "New"),
        ("assigned", "Assigned"),
        ("scheduled", "Scheduled"),
        ("technician_visit", "Technician Visit"),
        ("waiting_parts", "Waiting for Parts"),
        ("resolved", "Resolved"),
        ("closed", "Closed"),
    ]
    PRIORITY_CHOICES = [("low", "Low"), ("normal", "Normal"), ("high", "High"), ("urgent", "Urgent")]

    complaint_number = models.CharField(max_length=20, unique=True, blank=True)
    customer = models.ForeignKey("crm.Customer", on_delete=models.CASCADE, related_name="complaints")
    order = models.ForeignKey("sales.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="complaints")
    category = models.ForeignKey("core.ServiceCategory", on_delete=models.SET_NULL, null=True, blank=True)
    product = models.CharField(max_length=150, blank=True)
    complaint_date = models.DateField(auto_now_add=True)
    description = models.TextField(blank=True)
    assigned_technician = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="service_jobs"
    )
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="normal")
    scheduled_date = models.DateField(null=True, blank=True)
    resolution = models.TextField(blank=True)
    spare_parts = models.CharField(max_length=255, blank=True)
    service_charges = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_warranty = models.BooleanField(default=True)
    completion_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new")

    history = HistoricalRecords()

    class Meta:
        ordering = ["-complaint_date"]

    def __str__(self):
        return self.complaint_number

    def save(self, *args, **kwargs):
        if not self.complaint_number:
            from apps.core.numbering import get_next_number

            self.complaint_number = get_next_number("complaint")
        if self.assigned_technician and self.status == "new":
            self.status = "assigned"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("aftersales:complaint_detail", args=[self.pk])
