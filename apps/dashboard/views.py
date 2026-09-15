import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render
from django.utils import timezone

from apps.aftersales.models import ServiceComplaint, Warranty
from apps.core.models import LeadStatus
from apps.crm.models import FollowUp, Lead
from apps.logistics.models import Dispatch, Installation
from apps.measurement.models import FinalMeasurementRequest, MeasurementRequest
from apps.production.models import ProductionSheet, ProductionTask, QualityCheck
from apps.sales.models import Order, Quotation


def _dashboard_mode(user):
    if user.is_superuser or user.is_staff or user.has_role("Super Admin", "Management"):
        return "management"
    if user.has_role("Production Manager", "Production Staff", "Quality Control"):
        return "production"
    if user.has_role("Dispatch Staff"):
        return "dispatch"
    if user.has_role("Installation Team"):
        return "installation"
    if user.has_role("Service/Maintenance Staff"):
        return "service"
    if user.has_role("Measurement Staff"):
        return "measurement"
    return "sales"  # Sales Manager, Salesperson, Quotation Staff, Admin Staff, fallback


@login_required
def home(request):
    user = request.user
    mode = _dashboard_mode(user)
    is_management = mode == "management"
    scope_to_user = not is_management

    today = timezone.now().date()
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    leads = Lead.objects.all()
    orders = Order.objects.all()
    if scope_to_user:
        leads = leads.filter(assigned_salesperson=user)
        orders = orders.filter(salesperson=user)

    crm_stats = {
        "total_leads": leads.count(),
        "new_leads": leads.filter(created_date__date=today).count(),
        "leads_assigned": leads.exclude(assigned_salesperson__isnull=True).count(),
        "leads_pending": leads.filter(status__is_won=False, status__is_lost=False).count(),
        "won_leads": leads.filter(status__is_won=True).count(),
        "lost_leads": leads.filter(status__is_lost=True).count(),
    }
    total_closed = crm_stats["won_leads"] + crm_stats["lost_leads"]
    crm_stats["conversion_percent"] = round(crm_stats["won_leads"] / total_closed * 100, 1) if total_closed else 0

    sales_stats = {
        "today_sales": orders.filter(confirmed_at__date=today).aggregate(v=Sum("final_value"))["v"] or 0,
        "month_sales": orders.filter(confirmed_at__date__gte=month_start).aggregate(v=Sum("final_value"))["v"] or 0,
        "year_sales": orders.filter(confirmed_at__date__gte=year_start).aggregate(v=Sum("final_value"))["v"] or 0,
        "pending_quotations": Quotation.objects.filter(status__in=["draft", "sent", "negotiation"]).count(),
    }

    followups = FollowUp.objects.filter(lead__in=leads)
    sales_stats["followups_today"] = followups.filter(next_followup_date=today).count()
    sales_stats["followups_overdue"] = followups.filter(next_followup_date__lt=today).count()

    production_stats = {
        "awaiting_final_measurement": FinalMeasurementRequest.objects.exclude(status="approved").count(),
        "production_pending": ProductionSheet.objects.filter(status="pending").count(),
        "production_in_progress": ProductionSheet.objects.filter(status__in=["approved", "in_production"]).count(),
        "production_completed": ProductionSheet.objects.filter(status="completed").count(),
        "qc_pending": QualityCheck.objects.filter(status="pending").count(),
        "dispatch_pending": Dispatch.objects.filter(status="pending").count(),
        "installation_pending": Installation.objects.exclude(status="completed").count(),
        "my_open_tasks": ProductionTask.objects.filter(assigned_to=user).exclude(status="completed").count(),
    }

    installation_stats = {
        "scheduled": Installation.objects.filter(status="scheduled").count(),
        "in_progress": Installation.objects.filter(status="in_progress").count(),
        "completed": Installation.objects.filter(status="completed").count(),
        "handover_pending": Installation.objects.filter(status="completed", handover__isnull=True).count(),
        "site_not_ready": Installation.objects.filter(status="site_not_ready").count(),
    }

    dispatch_stats = {
        "pending": Dispatch.objects.filter(status="pending").count(),
        "dispatched_today": Dispatch.objects.filter(status="dispatched", dispatch_date=today).count(),
    }

    service_stats = {
        "open": ServiceComplaint.objects.exclude(status__in=["resolved", "closed"]).count(),
        "assigned": ServiceComplaint.objects.filter(status="assigned", assigned_technician=user).count() if not is_management else ServiceComplaint.objects.filter(status="assigned").count(),
        "resolved": ServiceComplaint.objects.filter(status="resolved").count(),
        "warranty_active": Warranty.objects.filter(warranty_end_date__gte=today).count(),
    }

    measurement_stats = {
        "assigned_to_me": MeasurementRequest.objects.filter(assigned_to=user).exclude(status__in=["completed", "cancelled"]).count(),
        "scheduled": MeasurementRequest.objects.filter(assigned_to=user, status="scheduled").count(),
        "completed_this_month": MeasurementRequest.objects.filter(assigned_to=user, status="completed", completed_at__date__gte=month_start).count(),
    }

    funnel_statuses = LeadStatus.objects.filter(is_won=False, is_lost=False).order_by("sequence")
    funnel = [{"label": s.name, "count": leads.filter(status=s).count()} for s in funnel_statuses]
    funnel.append({"label": "Won", "count": crm_stats["won_leads"]})

    months, monthly_values = [], []
    for i in range(5, -1, -1):
        month_date = today.replace(day=1) - timedelta(days=30 * i)
        months.append(month_date.strftime("%b %Y"))
        monthly_values.append(
            float(
                Order.objects.filter(confirmed_at__year=month_date.year, confirmed_at__month=month_date.month)
                .aggregate(v=Sum("final_value"))["v"] or 0
            )
        )

    my_tasks = []
    for m in MeasurementRequest.objects.filter(assigned_to=user).exclude(status__in=["completed", "cancelled"])[:10]:
        my_tasks.append({"label": f"Measurement: {m.measurement_id}", "url": m.get_absolute_url(), "due": m.scheduled_date, "icon": "fa-ruler-combined"})
    for f in FinalMeasurementRequest.objects.filter(assigned_to=user).exclude(status__in=["approved"])[:10]:
        my_tasks.append({"label": f"Final Measurement: {f.final_measurement_id}", "url": f.get_absolute_url(), "due": f.scheduled_date, "icon": "fa-ruler"})
    for t in ProductionTask.objects.filter(assigned_to=user).exclude(status="completed").select_related("production_sheet", "stage")[:10]:
        my_tasks.append({"label": f"{t.stage.name}: {t.production_sheet.production_number}", "url": t.production_sheet.get_absolute_url(), "due": None, "icon": "fa-industry"})
    for i in Installation.objects.filter(installation_team=user).exclude(status="completed")[:10]:
        my_tasks.append({"label": f"Installation: {i.installation_id}", "url": i.get_absolute_url(), "due": i.scheduled_date, "icon": "fa-screwdriver-wrench"})
    for c in ServiceComplaint.objects.filter(assigned_technician=user).exclude(status__in=["resolved", "closed"])[:10]:
        my_tasks.append({"label": f"Service: {c.complaint_number}", "url": c.get_absolute_url(), "due": c.scheduled_date, "icon": "fa-headset"})

    context = {
        "dashboard_mode": mode,
        "is_management": is_management,
        "crm_stats": crm_stats,
        "sales_stats": sales_stats,
        "production_stats": production_stats,
        "installation_stats": installation_stats,
        "dispatch_stats": dispatch_stats,
        "service_stats": service_stats,
        "measurement_stats": measurement_stats,
        "funnel": funnel,
        "chart_months": json.dumps(months),
        "chart_values": json.dumps(monthly_values),
        "my_tasks": my_tasks,
    }
    return render(request, "dashboard/home.html", context)
