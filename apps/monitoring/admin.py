from django.contrib import admin

from .models import Advance, Attendance, DayAdvance, ReopenedMonth, SiteStop, Worker, WorkDay


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ("name", "designation", "phone", "monthly_salary", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "phone", "designation")


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("date", "worker", "status", "overtime_hours")
    list_filter = ("status", "date")
    date_hierarchy = "date"


@admin.register(Advance)
class AdvanceAdmin(admin.ModelAdmin):
    list_display = ("month", "worker", "deduction")


@admin.register(DayAdvance)
class DayAdvanceAdmin(admin.ModelAdmin):
    list_display = ("date", "worker", "amount")
    date_hierarchy = "date"


@admin.register(SiteStop)
class SiteStopAdmin(admin.ModelAdmin):
    list_display = ("recorded_at", "user", "latitude", "longitude", "remark")
    list_filter = ("user",)


admin.site.register(WorkDay)
admin.site.register(ReopenedMonth)
