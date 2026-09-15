from django.conf import settings
from django.db import models
from django.urls import reverse
from simple_history.models import HistoricalRecords

from apps.core.models import ProductionStageTemplate, QCChecklistItem


class ProductionSheet(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending Preparation"),
        ("submitted", "Submitted for Approval"),
        ("approved", "Approved"),
        ("in_production", "In Production"),
        ("completed", "Completed"),
    ]

    production_number = models.CharField(max_length=20, unique=True, blank=True)
    order = models.OneToOneField("sales.Order", on_delete=models.CASCADE, related_name="production_sheet")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    prepared_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.production_number

    def save(self, *args, **kwargs):
        if not self.production_number:
            from apps.core.numbering import get_next_number

            self.production_number = get_next_number("production_sheet")
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("production:sheet_detail", args=[self.pk])

    def progress_percent(self):
        total = self.tasks.count()
        if not total:
            return 0
        done = self.tasks.filter(status="completed").count()
        return round(done / total * 100)


class ProductionSheetItem(models.Model):
    production_sheet = models.ForeignKey(ProductionSheet, on_delete=models.CASCADE, related_name="items")
    window_door_number = models.CharField(max_length=30)
    quantity = models.PositiveIntegerField(default=1)
    width = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    height = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    profile = models.CharField(max_length=100, blank=True)
    colour = models.CharField(max_length=50, blank=True)
    glass = models.CharField(max_length=100, blank=True)
    glass_thickness = models.CharField(max_length=30, blank=True)
    hardware = models.CharField(max_length=150, blank=True)
    handle = models.CharField(max_length=100, blank=True)
    reinforcement = models.CharField(max_length=100, blank=True)
    mesh = models.CharField(max_length=100, blank=True)
    accessories = models.CharField(max_length=200, blank=True)
    opening_direction = models.CharField(max_length=100, blank=True)
    manufacturing_specs = models.TextField(blank=True)
    installation_requirements = models.TextField(blank=True)

    class Meta:
        ordering = ["window_door_number"]

    def __str__(self):
        return self.window_door_number


class ProductionTask(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("started", "Started"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("hold", "Hold"),
        ("rework", "Rework"),
    ]

    production_sheet = models.ForeignKey(ProductionSheet, on_delete=models.CASCADE, related_name="tasks")
    stage = models.ForeignKey(ProductionStageTemplate, on_delete=models.PROTECT)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="production_tasks")
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="pending")
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["stage__sequence"]

    def __str__(self):
        return f"{self.production_sheet.production_number} - {self.stage.name}"


class QualityCheck(models.Model):
    STATUS_CHOICES = [("pending", "Pending"), ("approved", "Approved"), ("rework_required", "Rework Required"), ("rejected", "Rejected")]

    production_sheet = models.OneToOneField(ProductionSheet, on_delete=models.CASCADE, related_name="quality_check")
    checked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    remarks = models.TextField(blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"QC - {self.production_sheet.production_number}"


class QCChecklistResult(models.Model):
    quality_check = models.ForeignKey(QualityCheck, on_delete=models.CASCADE, related_name="results")
    checklist_item = models.ForeignKey(QCChecklistItem, on_delete=models.CASCADE)
    passed = models.BooleanField(default=True)
    remarks = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.checklist_item} - {'OK' if self.passed else 'Fail'}"
