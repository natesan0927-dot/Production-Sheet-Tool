from django.contrib import admin

from apps.logistics import models


@admin.register(models.Dispatch)
class DispatchAdmin(admin.ModelAdmin):
    list_display = ("dispatch_id", "order", "status", "dispatch_date", "vehicle_number")
    list_filter = ("status",)


class SiteNotReadyInline(admin.TabularInline):
    model = models.SiteNotReadyLog
    extra = 0


@admin.register(models.Installation)
class InstallationAdmin(admin.ModelAdmin):
    list_display = ("installation_id", "order", "team_leader", "status", "scheduled_date", "actual_date")
    list_filter = ("status",)
    inlines = [SiteNotReadyInline]


@admin.register(models.Handover)
class HandoverAdmin(admin.ModelAdmin):
    list_display = ("order", "installation_date", "customer_confirmation", "generated_at")
