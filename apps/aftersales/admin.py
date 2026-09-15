from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from apps.aftersales import models


@admin.register(models.Warranty)
class WarrantyAdmin(admin.ModelAdmin):
    list_display = ("certificate_number", "order", "warranty_start_date", "warranty_end_date")
    search_fields = ("certificate_number", "order__order_number")


@admin.register(models.ServiceComplaint)
class ServiceComplaintAdmin(SimpleHistoryAdmin):
    list_display = ("complaint_number", "customer", "status", "priority", "assigned_technician", "complaint_date")
    list_filter = ("status", "priority", "is_warranty")
    search_fields = ("complaint_number", "customer__customer_name")
