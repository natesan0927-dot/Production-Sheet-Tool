from django.contrib import admin

from apps.core import models


@admin.register(models.CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not models.CompanyProfile.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(models.NumberSequence)
class NumberSequenceAdmin(admin.ModelAdmin):
    list_display = ("doc_type", "prefix", "year", "last_number", "padding")
    search_fields = ("doc_type", "prefix")


@admin.register(models.LeadSource)
class LeadSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_editable = ("is_active",)


@admin.register(models.LeadStatus)
class LeadStatusAdmin(admin.ModelAdmin):
    list_display = ("name", "sequence", "is_won", "is_lost", "is_default", "color")
    list_editable = ("sequence", "is_won", "is_lost", "is_default", "color")


@admin.register(models.LostReason)
class LostReasonAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_editable = ("is_active",)


@admin.register(models.Competitor)
class CompetitorAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(models.ProfileSeries)
class ProfileSeriesAdmin(admin.ModelAdmin):
    list_display = ("series", "brand", "colour")
    search_fields = ("series", "brand")


@admin.register(models.GlassType)
class GlassTypeAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(models.HardwareType)
class HardwareTypeAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(models.AccessoryType)
class AccessoryTypeAdmin(admin.ModelAdmin):
    list_display = ("name",)


class PaymentTermStepInline(admin.TabularInline):
    model = models.PaymentTermStep
    extra = 1


@admin.register(models.PaymentTermTemplate)
class PaymentTermTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "is_default")
    inlines = [PaymentTermStepInline]


@admin.register(models.ProductionStageTemplate)
class ProductionStageTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "sequence", "is_active")
    list_editable = ("sequence", "is_active")


@admin.register(models.QCChecklistItem)
class QCChecklistItemAdmin(admin.ModelAdmin):
    list_display = ("name", "sequence", "is_active")
    list_editable = ("sequence", "is_active")


@admin.register(models.InstallationChecklistItem)
class InstallationChecklistItemAdmin(admin.ModelAdmin):
    list_display = ("name", "sequence", "is_active")
    list_editable = ("sequence", "is_active")


@admin.register(models.ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_editable = ("is_active",)


@admin.register(models.DocumentTemplate)
class DocumentTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "updated_at")


@admin.register(models.Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("doc_type", "content_type", "object_id", "version", "uploaded_by", "uploaded_at", "auto_generated")
    list_filter = ("doc_type", "auto_generated")
    readonly_fields = ("uploaded_at",)


@admin.register(models.Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("category", "content_type", "object_id", "uploaded_by", "uploaded_at")
    list_filter = ("category",)


@admin.register(models.EmployeeTask)
class EmployeeTaskAdmin(admin.ModelAdmin):
    list_display = ("task_id", "title", "assigned_to", "department", "priority", "status", "due_date")
    list_filter = ("status", "priority", "department")


@admin.register(models.Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "verb", "is_read", "created_at")
    list_filter = ("is_read",)
