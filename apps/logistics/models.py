from django.conf import settings
from django.db import models
from django.urls import reverse


class Dispatch(models.Model):
    STATUS_CHOICES = [("pending", "Pending"), ("dispatched", "Dispatched")]

    dispatch_id = models.CharField(max_length=20, unique=True, blank=True)
    order = models.OneToOneField("sales.Order", on_delete=models.CASCADE, related_name="dispatch")
    dispatch_date = models.DateField(null=True, blank=True)
    vehicle_number = models.CharField(max_length=30, blank=True)
    driver = models.CharField(max_length=100, blank=True)
    driver_phone = models.CharField(max_length=20, blank=True)
    transporter = models.CharField(max_length=100, blank=True)
    number_of_packages = models.PositiveIntegerField(null=True, blank=True)
    package_details = models.TextField(blank=True)
    delivery_address = models.TextField(blank=True)
    expected_delivery_date = models.DateField(null=True, blank=True)
    remarks = models.TextField(blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="pending")
    dispatched_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.dispatch_id

    def save(self, *args, **kwargs):
        if not self.dispatch_id:
            from apps.core.numbering import get_next_number

            self.dispatch_id = get_next_number("dispatch")
        if not self.delivery_address and self.order_id:
            self.delivery_address = self.order.customer.project_address or self.order.customer.address
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("logistics:dispatch_detail", args=[self.pk])


class Installation(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("scheduled", "Scheduled"),
        ("site_not_ready", "Site Not Ready"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("revisit_required", "Revisit Required"),
    ]

    installation_id = models.CharField(max_length=20, unique=True, blank=True)
    order = models.OneToOneField("sales.Order", on_delete=models.CASCADE, related_name="installation")
    site_address = models.TextField(blank=True)
    team_leader = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="installations_led"
    )
    installation_team = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="installation_jobs")
    scheduled_date = models.DateField(null=True, blank=True)
    actual_date = models.DateField(null=True, blank=True)
    site_readiness = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    remarks = models.TextField(blank=True)
    customer_signature = models.ImageField(upload_to="signatures/%Y/%m/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.installation_id

    def save(self, *args, **kwargs):
        if not self.installation_id:
            from apps.core.numbering import get_next_number

            self.installation_id = get_next_number("installation")
        if not self.site_address and self.order_id:
            self.site_address = self.order.customer.project_address or self.order.customer.address
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("logistics:installation_detail", args=[self.pk])


class SiteNotReadyLog(models.Model):
    REASON_CHOICES = [
        ("civil_work", "Civil work pending"),
        ("flooring", "Flooring pending"),
        ("electrical", "Electrical work pending"),
        ("plastering", "Plastering pending"),
        ("customer_unavailable", "Customer unavailable"),
        ("site_inaccessible", "Site inaccessible"),
        ("other", "Other"),
    ]

    installation = models.ForeignKey(Installation, on_delete=models.CASCADE, related_name="site_not_ready_logs")
    reason = models.CharField(max_length=25, choices=REASON_CHOICES)
    other_text = models.CharField(max_length=255, blank=True)
    logged_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    logged_at = models.DateTimeField(auto_now_add=True)
    rescheduled_to = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-logged_at"]

    def __str__(self):
        return f"{self.installation.installation_id} - {self.get_reason_display()}"


class Handover(models.Model):
    installation = models.OneToOneField(Installation, on_delete=models.CASCADE, related_name="handover")
    order = models.OneToOneField("sales.Order", on_delete=models.CASCADE, related_name="handover")
    installation_date = models.DateField(null=True, blank=True)
    installed_items_summary = models.TextField(blank=True)
    customer_confirmation = models.BooleanField(default=False)
    remarks = models.TextField(blank=True)
    customer_signature = models.ImageField(upload_to="signatures/%Y/%m/", blank=True, null=True)
    company_representative = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    certificate_pdf = models.FileField(upload_to="handover/%Y/%m/", blank=True, null=True)

    def __str__(self):
        return f"Handover - {self.order.order_number}"

    def get_absolute_url(self):
        return reverse("logistics:installation_detail", args=[self.installation_id])
