from django.contrib import admin

from .models import FollowUp, Lead, LeadFile, Notification, SalesTarget


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("lead_number", "customer_name", "assigned_to", "status", "updated_at")
    list_filter = ("status", "assigned_to", "fabrication_column")
    search_fields = ("lead_number", "customer_name", "phone", "site_location")


@admin.register(LeadFile)
class LeadFileAdmin(admin.ModelAdmin):
    list_display = ("lead", "kind", "uploaded_by", "uploaded_at")
    list_filter = ("kind",)


@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ("lead", "date", "time", "done")
    list_filter = ("done",)


@admin.register(SalesTarget)
class SalesTargetAdmin(admin.ModelAdmin):
    list_display = ("salesperson", "month", "amount")


admin.site.register(Notification)
