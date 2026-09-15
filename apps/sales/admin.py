from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from apps.sales import models


class QuotationItemInline(admin.TabularInline):
    model = models.QuotationItem
    extra = 0


@admin.register(models.Quotation)
class QuotationAdmin(SimpleHistoryAdmin):
    list_display = ("quotation_number", "customer", "status", "total_value", "prepared_by", "created_at")
    list_filter = ("status",)
    search_fields = ("root_number", "customer__customer_name")
    inlines = [QuotationItemInline]


class OrderItemInline(admin.TabularInline):
    model = models.OrderItem
    extra = 0


class PaymentInline(admin.TabularInline):
    model = models.Payment
    extra = 0


@admin.register(models.Order)
class OrderAdmin(SimpleHistoryAdmin):
    list_display = ("order_number", "customer", "status", "final_value", "salesperson", "confirmed_at")
    list_filter = ("status",)
    search_fields = ("order_number", "customer__customer_name")
    inlines = [OrderItemInline, PaymentInline]


@admin.register(models.SalesTarget)
class SalesTargetAdmin(admin.ModelAdmin):
    list_display = ("salesperson", "team_name", "branch", "year", "month", "target_amount")
    list_filter = ("year", "month")


@admin.register(models.CustomerAcquisitionForm)
class CustomerAcquisitionFormAdmin(admin.ModelAdmin):
    list_display = ("order", "version", "generated_at", "generated_by")


@admin.register(models.Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "amount", "mode", "date", "recorded_by")
    list_filter = ("mode",)
