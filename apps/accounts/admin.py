from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import Department, User


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_editable = ("is_active",)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "employee_id", "get_full_name", "department", "designation", "is_active", "is_staff")
    list_filter = ("is_active", "is_staff", "department", "groups")
    search_fields = ("username", "employee_id", "first_name", "last_name", "email", "mobile")

    fieldsets = BaseUserAdmin.fieldsets + (
        ("Employee Details", {"fields": ("employee_id", "mobile", "department", "designation", "photo")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Employee Details", {"fields": ("employee_id", "mobile", "department", "designation", "email")}),
    )
