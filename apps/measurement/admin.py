from django.contrib import admin

from apps.measurement import models


class MeasurementItemInline(admin.TabularInline):
    model = models.MeasurementItem
    extra = 0


@admin.register(models.MeasurementRequest)
class MeasurementRequestAdmin(admin.ModelAdmin):
    list_display = ("measurement_id", "customer", "assigned_to", "status", "priority", "requested_date", "scheduled_date")
    list_filter = ("status", "priority")
    search_fields = ("measurement_id", "customer__customer_name")
    inlines = [MeasurementItemInline]


class FinalMeasurementItemInline(admin.TabularInline):
    model = models.FinalMeasurementItem
    extra = 0


@admin.register(models.FinalMeasurementRequest)
class FinalMeasurementRequestAdmin(admin.ModelAdmin):
    list_display = ("final_measurement_id", "order", "assigned_to", "status", "scheduled_date")
    list_filter = ("status",)
    inlines = [FinalMeasurementItemInline]
