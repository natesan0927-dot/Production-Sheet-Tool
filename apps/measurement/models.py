from django.conf import settings
from django.db import models
from django.urls import reverse

from apps.core.models import AccessoryType, GlassType, HardwareType, ProfileSeries


class MeasurementRequest(models.Model):
    STATUS_CHOICES = [
        ("requested", "Requested"),
        ("assigned", "Assigned"),
        ("scheduled", "Scheduled"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("revisit_required", "Revisit Required"),
        ("cancelled", "Cancelled"),
    ]
    PRIORITY_CHOICES = [("low", "Low"), ("normal", "Normal"), ("high", "High")]

    measurement_id = models.CharField(max_length=20, unique=True, blank=True)
    lead = models.ForeignKey("crm.Lead", on_delete=models.CASCADE, related_name="measurement_requests")
    customer = models.ForeignKey("crm.Customer", on_delete=models.CASCADE, related_name="measurement_requests")
    site_address = models.TextField(blank=True)
    contact_person = models.CharField(max_length=150, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="measurement_jobs"
    )
    requested_date = models.DateField(auto_now_add=True)
    scheduled_date = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="normal")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="requested")
    instructions = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-requested_date"]

    def __str__(self):
        return self.measurement_id

    def save(self, *args, **kwargs):
        if not self.measurement_id:
            from apps.core.numbering import get_next_number

            self.measurement_id = get_next_number("measurement")
        if not self.site_address and self.customer_id:
            self.site_address = self.customer.project_address or self.customer.address
        if not self.contact_person and self.customer_id:
            self.contact_person = self.customer.contact_person or self.customer.customer_name
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("measurement:request_detail", args=[self.pk])


class MeasurementItem(models.Model):
    measurement_request = models.ForeignKey(MeasurementRequest, on_delete=models.CASCADE, related_name="items")
    window_number = models.CharField(max_length=30)
    room_location = models.CharField(max_length=100, blank=True)
    width = models.DecimalField(max_digits=8, decimal_places=2, help_text="mm")
    height = models.DecimalField(max_digits=8, decimal_places=2, help_text="mm")
    quantity = models.PositiveIntegerField(default=1)
    window_type = models.CharField(max_length=100, blank=True)
    door_type = models.CharField(max_length=100, blank=True)
    opening_type = models.CharField(max_length=100, blank=True)
    glass_type = models.ForeignKey(GlassType, on_delete=models.SET_NULL, null=True, blank=True)
    glass_thickness = models.CharField(max_length=30, blank=True)
    profile_series = models.ForeignKey(ProfileSeries, on_delete=models.SET_NULL, null=True, blank=True)
    profile_colour = models.CharField(max_length=50, blank=True)
    hardware = models.ForeignKey(HardwareType, on_delete=models.SET_NULL, null=True, blank=True)
    handle_type = models.CharField(max_length=100, blank=True)
    mesh = models.CharField(max_length=100, blank=True)
    reinforcement = models.CharField(max_length=100, blank=True)
    accessories = models.ManyToManyField(AccessoryType, blank=True)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["window_number"]

    def __str__(self):
        return f"{self.window_number} ({self.width}x{self.height})"


class FinalMeasurementRequest(models.Model):
    """Independent, separate final measurement carried out after order confirmation."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("assigned", "Assigned"),
        ("scheduled", "Scheduled"),
        ("completed", "Completed"),
        ("correction_required", "Correction Required"),
        ("approved", "Approved"),
    ]

    final_measurement_id = models.CharField(max_length=20, unique=True, blank=True)
    order = models.ForeignKey("sales.Order", on_delete=models.CASCADE, related_name="final_measurements")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="final_measurement_jobs"
    )
    scheduled_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default="pending")
    site_readiness = models.CharField(max_length=150, blank=True)
    special_remarks = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return self.final_measurement_id

    def save(self, *args, **kwargs):
        if not self.final_measurement_id:
            from apps.core.numbering import get_next_number

            self.final_measurement_id = get_next_number("final_measurement")
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("measurement:final_detail", args=[self.pk])


class FinalMeasurementItem(models.Model):
    final_measurement = models.ForeignKey(FinalMeasurementRequest, on_delete=models.CASCADE, related_name="items")
    window_number = models.CharField(max_length=30)
    final_width = models.DecimalField(max_digits=8, decimal_places=2)
    final_height = models.DecimalField(max_digits=8, decimal_places=2)
    opening_direction = models.CharField(max_length=100, blank=True)
    frame_details = models.CharField(max_length=200, blank=True)
    sash_details = models.CharField(max_length=200, blank=True)
    glass_details = models.CharField(max_length=200, blank=True)
    hardware_details = models.CharField(max_length=200, blank=True)
    colour = models.CharField(max_length=50, blank=True)
    profile = models.CharField(max_length=100, blank=True)
    reinforcement = models.CharField(max_length=100, blank=True)
    mesh = models.CharField(max_length=100, blank=True)
    accessories = models.CharField(max_length=200, blank=True)
    installation_requirements = models.TextField(blank=True)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["window_number"]

    def __str__(self):
        return f"{self.window_number} ({self.final_width}x{self.final_height})"
