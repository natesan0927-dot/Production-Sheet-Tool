from django.db.models import Count, Sum
from django.shortcuts import render
from django.utils import timezone

from apps.core.exports import as_download_response, workbook_response
from apps.core.mixins import require_section
from apps.crm.models import Lead, LostLeadDetail
from apps.production.models import ProductionSheet
from apps.sales.models import Order, Quotation


@require_section("insights")
def index(request):
    return render(request, "reports/index.html")


@require_section("insights")
def monthly_sales_report(request):
    today = timezone.now().date()
    year = int(request.GET.get("year", today.year))
    month = int(request.GET.get("month", today.month))

    orders = Order.objects.filter(confirmed_at__year=year, confirmed_at__month=month)
    quotations = Quotation.objects.filter(created_at__year=year, created_at__month=month)
    leads = Lead.objects.filter(created_date__year=year, created_date__month=month)

    by_salesperson = (
        orders.values("salesperson__first_name", "salesperson__last_name")
        .annotate(total=Sum("final_value"), count=Count("id"))
        .order_by("-total")
    )

    context = {
        "year": year, "month": month,
        "total_leads": leads.count(),
        "quotations_issued": quotations.count(),
        "quotation_value": quotations.aggregate(v=Sum("total_value"))["v"] or 0,
        "won_orders": orders.count(),
        "won_value": orders.aggregate(v=Sum("final_value"))["v"] or 0,
        "by_salesperson": by_salesperson,
    }

    if request.GET.get("export") == "excel":
        headers = ["Salesperson", "Orders", "Value"]
        rows = [[f"{r['salesperson__first_name'] or ''} {r['salesperson__last_name'] or ''}".strip() or "Unassigned", r["count"], float(r["total"] or 0)] for r in by_salesperson]
        exported = workbook_response(headers, rows, filename=f"MonthlySalesReport_{year}_{month}.xlsx")
        return as_download_response(exported)

    return render(request, "reports/monthly_sales.html", context)


@require_section("insights")
def lost_lead_report(request):
    details = LostLeadDetail.objects.select_related("lead", "competitor", "reason")
    by_competitor = details.exclude(competitor__isnull=True).values("competitor__name").annotate(count=Count("id")).order_by("-count")
    by_reason = details.values("reason_category").annotate(count=Count("id")).order_by("-count")
    by_salesperson = details.values("lead__assigned_salesperson__first_name", "lead__assigned_salesperson__last_name").annotate(count=Count("id")).order_by("-count")

    context = {"details": details, "by_competitor": by_competitor, "by_reason": by_reason, "by_salesperson": by_salesperson}

    if request.GET.get("export") == "excel":
        headers = ["Lead", "Customer", "Lost Date", "Reason", "Competitor", "Competitor Price", "Our Price"]
        rows = [
            [d.lead.lead_id, d.lead.customer.customer_name, str(d.lost_date), d.get_reason_category_display(), str(d.competitor or ""), str(d.competitor_price or ""), str(d.customer_quoted_price or "")]
            for d in details
        ]
        exported = workbook_response(headers, rows, filename="LostLeadAnalysis.xlsx")
        return as_download_response(exported)

    return render(request, "reports/lost_leads.html", context)


@require_section("insights")
def production_report(request):
    sheets = ProductionSheet.objects.select_related("order").order_by("-created_at")
    context = {"sheets": sheets}
    if request.GET.get("export") == "excel":
        headers = ["Production #", "Order", "Status", "Progress %", "Created"]
        rows = [[s.production_number, s.order.order_number, s.get_status_display(), s.progress_percent(), str(s.created_at.date())] for s in sheets]
        exported = workbook_response(headers, rows, filename="ProductionReport.xlsx")
        return as_download_response(exported)
    return render(request, "reports/production.html", context)


@require_section("insights")
def customer_report(request):
    from apps.crm.models import Customer

    customers = Customer.objects.all().order_by("-created_date")
    context = {"customers": customers}
    if request.GET.get("export") == "excel":
        headers = ["Code", "Name", "Mobile", "City", "Type", "Salesperson", "Status"]
        rows = [[c.customer_code, c.customer_name, c.mobile_number, c.city, c.get_customer_type_display(), str(c.assigned_salesperson or ""), c.get_customer_status_display()] for c in customers]
        exported = workbook_response(headers, rows, filename="CustomerReport.xlsx")
        return as_download_response(exported)
    return render(request, "reports/customers.html", context)
