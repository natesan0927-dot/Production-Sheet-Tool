from django.utils import timezone

from apps.core.notifications import notify_many


def create_dispatch_request(order, triggered_by=None):
    from apps.logistics.models import Dispatch

    dispatch, created = Dispatch.objects.get_or_create(order=order)
    if created:
        from apps.accounts.models import User

        dispatch_staff = User.objects.filter(groups__name__in=["Dispatch Staff", "Super Admin"], is_active=True).distinct()
        notify_many(dispatch_staff, f"Order ready for dispatch: {order.order_number}", url=dispatch.get_absolute_url(), related_object=dispatch)
    order.status = "qc"
    order.save(update_fields=["status"])
    return dispatch


def mark_dispatched(dispatch, user):
    from apps.logistics.models import Installation

    dispatch.status = "dispatched"
    dispatch.dispatched_by = user
    if not dispatch.dispatch_date:
        dispatch.dispatch_date = timezone.now().date()
    dispatch.save(update_fields=["status", "dispatched_by", "dispatch_date"])

    dispatch.order.status = "dispatch"
    dispatch.order.save(update_fields=["status"])

    if dispatch.order.salesperson:
        from apps.core.notifications import notify

        notify(
            dispatch.order.salesperson, f"Order dispatched: {dispatch.order.order_number}",
            url=dispatch.order.get_absolute_url(), related_object=dispatch.order,
        )

    installation, created = Installation.objects.get_or_create(order=dispatch.order)
    if created:
        from apps.accounts.models import User

        install_team = User.objects.filter(groups__name__in=["Installation Team", "Super Admin"], is_active=True).distinct()
        notify_many(install_team, f"Installation ready to schedule: {installation.installation_id}", url=installation.get_absolute_url(), related_object=installation)
    return installation


def mark_installation_completed(installation, user):
    installation.status = "completed"
    if not installation.actual_date:
        installation.actual_date = timezone.now().date()
    installation.save(update_fields=["status", "actual_date"])

    installation.order.status = "installation"
    installation.order.save(update_fields=["status"])

    from apps.core.notifications import notify

    if installation.order.salesperson:
        notify(installation.order.salesperson, f"Installation completed: {installation.installation_id}", url=installation.get_absolute_url(), related_object=installation)


def generate_handover(installation, user, customer_confirmation=True, remarks="", signature_file=None):
    from apps.core.exports import render_pdf_response
    from apps.core.models import Document
    from apps.logistics.models import Handover
    from django.contrib.contenttypes.models import ContentType
    from django.core.files.base import ContentFile

    order = installation.order
    handover, _ = Handover.objects.get_or_create(
        installation=installation, order=order,
        defaults={"installation_date": installation.actual_date},
    )
    handover.customer_confirmation = customer_confirmation
    handover.remarks = remarks
    handover.company_representative = user
    if signature_file:
        handover.customer_signature = signature_file
    handover.installed_items_summary = ", ".join(
        f"{i.description} x{i.quantity}" for i in order.items.all()
    )
    handover.save()

    exported = render_pdf_response(
        "logistics/pdf/handover_certificate.html", {"handover": handover, "order": order, "installation": installation},
        filename=f"Handover_{order.order_number}.pdf",
    )
    handover.certificate_pdf.save(exported.filename, ContentFile(exported.content), save=True)

    doc = Document(
        content_type=ContentType.objects.get_for_model(order), object_id=order.pk,
        doc_type="Handover Certificate", version=1, uploaded_by=user, auto_generated=True,
    )
    doc.file.save(exported.filename, ContentFile(exported.content), save=True)

    order.status = "handover"
    order.save(update_fields=["status"])

    from apps.aftersales.services import activate_warranty

    activate_warranty(order, user)
    return handover
