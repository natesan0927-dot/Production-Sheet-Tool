from django.utils import timezone

from apps.core.models import ProductionStageTemplate
from apps.core.notifications import notify_many


def create_production_sheet_request(order, triggered_by=None):
    from apps.production.models import ProductionSheet

    sheet, created = ProductionSheet.objects.get_or_create(order=order)
    if created:
        from apps.accounts.models import User

        admin_staff = User.objects.filter(groups__name__in=["Admin Staff", "Super Admin"], is_active=True).distinct()
        notify_many(admin_staff, f"Production sheet needed for {order.order_number}", url=sheet.get_absolute_url(), related_object=sheet)
    return sheet


def submit_production_sheet(sheet, user):
    sheet.status = "submitted"
    sheet.prepared_by = user
    sheet.submitted_at = timezone.now()
    sheet.save(update_fields=["status", "prepared_by", "submitted_at"])

    from apps.accounts.models import User

    managers = User.objects.filter(groups__name__in=["Production Manager", "Super Admin"], is_active=True).distinct()
    notify_many(managers, f"Production sheet ready for approval: {sheet.production_number}", url=sheet.get_absolute_url(), related_object=sheet)


def approve_production_sheet(sheet, user):
    from apps.production.models import ProductionTask

    sheet.status = "approved"
    sheet.approved_by = user
    sheet.approved_at = timezone.now()
    sheet.save(update_fields=["status", "approved_by", "approved_at"])

    for stage in ProductionStageTemplate.objects.filter(is_active=True).order_by("sequence"):
        ProductionTask.objects.get_or_create(production_sheet=sheet, stage=stage)

    sheet.order.status = "production"
    sheet.order.save(update_fields=["status"])


def maybe_complete_production(sheet):
    """Once every stage task is completed, close the sheet and kick off QC."""
    from apps.production.models import QualityCheck

    if sheet.status == "completed":
        return
    if sheet.tasks.exists() and not sheet.tasks.exclude(status="completed").exists():
        sheet.status = "completed"
        sheet.completed_at = timezone.now()
        sheet.save(update_fields=["status", "completed_at"])

        qc, _ = QualityCheck.objects.get_or_create(production_sheet=sheet)

        from apps.accounts.models import User

        qc_staff = User.objects.filter(groups__name__in=["Quality Control", "Super Admin"], is_active=True).distinct()
        notify_many(qc_staff, f"Quality check pending: {sheet.production_number}", url=sheet.get_absolute_url(), related_object=sheet)


def process_qc_result(quality_check, user, status, remarks=""):
    from apps.production.models import ProductionTask

    quality_check.status = status
    quality_check.checked_by = user
    quality_check.checked_at = timezone.now()
    quality_check.remarks = remarks
    quality_check.save(update_fields=["status", "checked_by", "checked_at", "remarks"])

    sheet = quality_check.production_sheet
    if status == "approved":
        from apps.logistics.services import create_dispatch_request

        create_dispatch_request(sheet.order, user)
    else:
        rework_stage = sheet.tasks.order_by("-stage__sequence").first()
        if rework_stage:
            ProductionTask.objects.create(production_sheet=sheet, stage=rework_stage.stage, status="rework", remarks=f"QC {status}: {remarks}")
            from apps.core.notifications import notify

            if rework_stage.assigned_to:
                notify(rework_stage.assigned_to, f"Rework required on {sheet.production_number}", url=sheet.get_absolute_url(), related_object=sheet)
