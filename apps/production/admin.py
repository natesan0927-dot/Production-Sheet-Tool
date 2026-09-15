from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from apps.production import models


class ProductionSheetItemInline(admin.TabularInline):
    model = models.ProductionSheetItem
    extra = 0


class ProductionTaskInline(admin.TabularInline):
    model = models.ProductionTask
    extra = 0


@admin.register(models.ProductionSheet)
class ProductionSheetAdmin(SimpleHistoryAdmin):
    list_display = ("production_number", "order", "status", "prepared_by", "approved_by", "created_at")
    list_filter = ("status",)
    inlines = [ProductionSheetItemInline, ProductionTaskInline]


@admin.register(models.ProductionTask)
class ProductionTaskAdmin(admin.ModelAdmin):
    list_display = ("production_sheet", "stage", "assigned_to", "status", "start_time", "end_time")
    list_filter = ("status", "stage")


class QCChecklistResultInline(admin.TabularInline):
    model = models.QCChecklistResult
    extra = 0


@admin.register(models.QualityCheck)
class QualityCheckAdmin(admin.ModelAdmin):
    list_display = ("production_sheet", "status", "checked_by", "checked_at")
    list_filter = ("status",)
    inlines = [QCChecklistResultInline]
