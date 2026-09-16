from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.http import HttpResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.exports import get_exporter
from apps.core.models import Document, Notification


def _safe_backup_copy(obj, exported_file):
    """
    Best-effort server-side backup copy under DOCUMENT_BACKUP_ROOT, in addition
    to the employee's own local download. Never blocks the user's download if
    the backup location is unavailable (e.g. network drive offline).
    """
    try:
        root = Path(settings.DOCUMENT_BACKUP_ROOT) / type(obj).__name__
        root.mkdir(parents=True, exist_ok=True)
        (root / exported_file.filename).write_bytes(exported_file.content)
    except OSError:
        pass


def _log_document(obj, exported_file, user, auto_generated=True):
    content_type = ContentType.objects.get_for_model(type(obj))
    version = Document.objects.filter(content_type=content_type, object_id=obj.pk).count() + 1
    doc = Document(
        content_type=content_type,
        object_id=obj.pk,
        doc_type=type(obj).__name__,
        version=version,
        uploaded_by=user if getattr(user, "is_authenticated", False) else None,
        auto_generated=auto_generated,
        description="Auto-generated local copy",
    )
    doc.file.save(exported_file.filename, ContentFile(exported_file.content), save=True)
    return doc


@login_required
def local_copy_download(request, app_label, model, pk):
    """
    Generates (or regenerates) the PDF/Excel export for one record, streams it
    to the browser as an attachment (so it saves straight to the employee's own
    Downloads folder), keeps a versioned copy in Document, and writes a second
    safety copy to DOCUMENT_BACKUP_ROOT on the server.
    """
    content_type = get_object_or_404(ContentType, app_label=app_label, model=model)
    model_class = content_type.model_class()
    if model_class is None:
        raise Http404("Unknown record type.")
    obj = get_object_or_404(model_class, pk=pk)

    exporter = get_exporter(model)
    if exporter is None:
        raise Http404("No local-copy export is available for this record type.")

    _kind, func = exporter
    exported_file = func(obj)

    _log_document(obj, exported_file, request.user)
    _safe_backup_copy(obj, exported_file)

    response = HttpResponse(exported_file.content, content_type=exported_file.content_type)
    response["Content-Disposition"] = f'attachment; filename="{exported_file.filename}"'
    return response


@login_required
def notifications_poll(request):
    """
    Polled every few seconds from the topbar bell so a notification created by
    someone else's action (another role finishing their step) shows up
    without the user having to reload or navigate anywhere.
    """
    from django.urls import reverse

    qs = request.user.notifications.all()[:8]
    items = [
        {
            "id": n.pk,
            "verb": n.verb,
            "url": n.get_absolute_url(),
            "read_url": reverse("core:notification_read", args=[n.pk]),
            "is_read": n.is_read,
            "since": naturaltime_short(n.created_at),
        }
        for n in qs
    ]
    return JsonResponse({"unread_count": request.user.notifications.filter(is_read=False).count(), "items": items})


def naturaltime_short(dt):
    from django.utils import timezone

    delta = timezone.now() - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


@login_required
def notification_list(request):
    notifications = request.user.notifications.all()[:100]
    return render(request, "core/notifications.html", {"notifications": notifications})


@login_required
def notification_mark_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notification.is_read = True
    notification.save(update_fields=["is_read"])
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    return redirect(notification.get_absolute_url())


@login_required
def notification_mark_all_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return redirect("core:notifications")


@login_required
def global_search(request):
    query = request.GET.get("q", "").strip()
    results = []
    if query:
        from apps.crm.models import Customer, Lead
        from apps.measurement.models import MeasurementRequest, FinalMeasurementRequest
        from apps.sales.models import Quotation, Order
        from apps.production.models import ProductionSheet
        from apps.aftersales.models import ServiceComplaint

        results.append(("Customers", Customer.objects.filter(
            models_q(query, ["customer_name", "mobile_number", "project_name"])
        )[:15]))
        results.append(("Leads", Lead.objects.filter(
            models_q(query, ["lead_id", "customer__customer_name", "project_name"])
        )[:15]))
        results.append(("Measurements", MeasurementRequest.objects.filter(
            models_q(query, ["measurement_id", "customer__customer_name"])
        )[:15]))
        results.append(("Final Measurements", FinalMeasurementRequest.objects.filter(
            models_q(query, ["final_measurement_id", "order__order_number"])
        )[:15]))
        results.append(("Quotations", Quotation.objects.filter(
            models_q(query, ["root_number", "customer__customer_name"])
        )[:15]))
        results.append(("Orders", Order.objects.filter(
            models_q(query, ["order_number", "customer__customer_name"])
        )[:15]))
        results.append(("Production Sheets", ProductionSheet.objects.filter(
            models_q(query, ["production_number", "order__order_number"])
        )[:15]))
        results.append(("Service Complaints", ServiceComplaint.objects.filter(
            models_q(query, ["complaint_number", "customer__customer_name"])
        )[:15]))

    return render(request, "core/search_results.html", {"query": query, "results": results})


def models_q(query, fields):
    from django.db.models import Q

    q = Q()
    for field in fields:
        q |= Q(**{f"{field}__icontains": query})
    return q


@login_required
def settings_hub(request):
    from apps.core.access import SECTION_ROLES

    if not (
        request.user.is_staff or request.user.is_superuser
        or request.user.groups.filter(name__in=SECTION_ROLES["settings"]).exists()
    ):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied("You do not have access to Admin Settings.")
    return render(request, "core/settings_hub.html")


@login_required
def guide(request):
    """
    Plain-language "what does my role do / how do I use this / what's the
    flow" page. Shows the signed-in user's own role by default; anyone whose
    nav_sections overlap another role's guide can switch to it too, which
    naturally covers Admin Staff/Management/Super Admin (who have every
    section) without any special-casing.
    """
    from apps.core.access import ROLE_PRIORITY, primary_role_label, user_sections
    from apps.core.guide_content import GUIDES, guide_icon

    viewer_sections = user_sections(request.user)
    viewer_primary = primary_role_label(request.user)

    def can_view(role):
        role_data = GUIDES.get(role)
        if not role_data:
            return False
        if role == viewer_primary:
            return True
        return any(section["nav_section"] in viewer_sections for section in role_data["sections"])

    requested = request.GET.get("role")
    if requested and can_view(requested):
        selected_role = requested
    elif viewer_primary in GUIDES:
        selected_role = viewer_primary
    else:
        selected_role = None

    browsable_roles = [role for role in ROLE_PRIORITY if can_view(role)]
    selected_guide = GUIDES.get(selected_role)

    return render(request, "core/guide.html", {
        "selected_role": selected_role,
        "guide": selected_guide,
        "guide_icon": guide_icon(selected_role) if selected_role else "fa-book-open",
        "browsable_roles": browsable_roles,
        "viewer_primary": viewer_primary,
    })
