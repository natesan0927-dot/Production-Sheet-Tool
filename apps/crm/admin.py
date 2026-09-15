from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from apps.crm import models


@admin.register(models.Customer)
class CustomerAdmin(SimpleHistoryAdmin):
    list_display = ("customer_code", "customer_name", "mobile_number", "city", "customer_type", "assigned_salesperson", "customer_status")
    list_filter = ("customer_type", "customer_status", "city")
    search_fields = ("customer_code", "customer_name", "mobile_number", "email", "project_name")


class FollowUpInline(admin.TabularInline):
    model = models.FollowUp
    extra = 0


@admin.register(models.Lead)
class LeadAdmin(SimpleHistoryAdmin):
    list_display = ("lead_id", "customer", "status", "assigned_salesperson", "priority", "expected_value", "created_date")
    list_filter = ("status", "priority", "lead_source")
    search_fields = ("lead_id", "customer__customer_name", "project_name")
    inlines = [FollowUpInline]


@admin.register(models.LeadAssignment)
class LeadAssignmentAdmin(admin.ModelAdmin):
    list_display = ("lead", "assigned_to", "assigned_by", "method", "assigned_at")
    list_filter = ("method",)


@admin.register(models.FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ("lead", "type", "date", "next_followup_date", "created_by")
    list_filter = ("type",)


@admin.register(models.CommunicationLog)
class CommunicationLogAdmin(admin.ModelAdmin):
    list_display = ("customer", "type", "date", "user")
    list_filter = ("type",)


@admin.register(models.LostLeadDetail)
class LostLeadDetailAdmin(admin.ModelAdmin):
    list_display = ("lead", "lost_date", "reason", "competitor", "competitor_price")
