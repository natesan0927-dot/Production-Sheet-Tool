"""
Resolves the full 12-stage order journey (Lead -> ... -> Handover & Warranty)
starting from ANY single object that belongs to one customer's order, so the
same stepper can be dropped onto the Lead, Quotation, Order, Measurement,
Final Measurement, Production Sheet, Quality Check, Dispatch and Installation
detail pages and always show the same, consistent picture of where that
order actually stands -- not just where the page you're looking at is.
"""
from django.urls import reverse

# The 5 pre-Order stages are derived from the Lead/Quotation/MeasurementRequest
# themselves (there's no Order yet to point at). The 7 post-Order stages are
# all driven off Order.status -- the one authoritative field for that half of
# the journey -- rather than letting 5 separate child-record status machines
# disagree with each other about which stage is "current".
STAGE_DEFS = [
    ("lead_created", "Lead Created"),
    ("assigned", "Assigned to Sales"),
    ("measurement", "Rough Measurement"),
    ("quotation", "Quotation"),
    ("followup_won", "Follow-up / Won-Lost"),
    ("order_confirmed", "Order Confirmed"),
    ("final_measurement", "Final Measurement"),
    ("production", "Production"),
    ("quality_check", "Quality Check"),
    ("dispatch", "Dispatch"),
    ("installation", "Installation"),
    ("handover", "Handover & Warranty"),
]
PRE_ORDER_KEYS = ["lead_created", "assigned", "measurement", "quotation", "followup_won"]
POST_ORDER_KEYS = [
    "order_confirmed", "final_measurement", "production", "quality_check", "dispatch", "installation", "handover",
]

ORDER_STATUS_SEQUENCE = [
    "confirmed", "caf_generated", "final_measurement", "production", "qc", "dispatch", "installation",
    "handover", "completed",
]
STATUS_TO_STAGE_KEY = {
    "confirmed": "order_confirmed",
    "caf_generated": "order_confirmed",
    "final_measurement": "final_measurement",
    "production": "production",
    "qc": "quality_check",
    "dispatch": "dispatch",
    "installation": "installation",
    "handover": "handover",
    "completed": "handover",
}


def _stage(key, label, state, url=None, sublabel=None, assignee=None):
    return {
        "key": key, "label": label, "state": state, "url": url, "sublabel": sublabel,
        "assignee": assignee, "is_current_page": False,
    }


def _user_label(user):
    return (user.get_full_name() or user.username) if user else None


def _resolve_lead_id(obj):
    from apps.crm.models import Lead
    from apps.logistics.models import Dispatch, Installation
    from apps.measurement.models import FinalMeasurementRequest, MeasurementRequest
    from apps.production.models import ProductionSheet, QualityCheck
    from apps.sales.models import Order, Quotation

    if isinstance(obj, Lead):
        return obj.pk
    if isinstance(obj, (Quotation, MeasurementRequest)):
        return obj.lead_id
    if isinstance(obj, Order):
        return obj.lead_id
    if isinstance(obj, (FinalMeasurementRequest, ProductionSheet, Dispatch, Installation)):
        return Order.objects.filter(pk=obj.order_id).values_list("lead_id", flat=True).first()
    if isinstance(obj, QualityCheck):
        return ProductionSheet.objects.filter(pk=obj.production_sheet_id).values_list(
            "order__lead_id", flat=True
        ).first()
    return None


def _current_page_key(obj):
    from apps.crm.models import Lead
    from apps.logistics.models import Dispatch, Installation
    from apps.measurement.models import FinalMeasurementRequest, MeasurementRequest
    from apps.production.models import ProductionSheet, QualityCheck
    from apps.sales.models import Order, Quotation

    mapping = [
        (Lead, "lead_created"), (Quotation, "quotation"), (Order, "order_confirmed"),
        (MeasurementRequest, "measurement"), (FinalMeasurementRequest, "final_measurement"),
        (ProductionSheet, "production"), (QualityCheck, "quality_check"),
        (Dispatch, "dispatch"), (Installation, "installation"),
    ]
    for cls, key in mapping:
        if isinstance(obj, cls):
            return key
    return None


def build_journey(obj):
    """Returns {"stages": [...], "banner": {...}|None, "service_badge": {...}} or None
    if the starting object can't be tied to a Lead (shouldn't normally happen)."""
    from apps.crm.models import Lead

    lead_id = _resolve_lead_id(obj)
    if lead_id is None:
        return None
    try:
        lead = Lead.objects.select_related(
            "status",
            "order", "order__production_sheet", "order__production_sheet__quality_check",
            "order__dispatch", "order__installation", "order__handover",
        ).get(pk=lead_id)
    except Lead.DoesNotExist:
        return None

    latest_mr = lead.measurement_requests.order_by("-requested_date", "-id").first()
    latest_q = lead.latest_quotation
    is_won = lead.is_won
    is_lost = lead.is_lost

    flags = {
        "lead_created": True,
        "assigned": bool(lead.assigned_salesperson_id),
        "measurement": bool(latest_mr and latest_mr.status == "completed"),
        "quotation": bool(latest_q and latest_q.status != "draft"),
        "followup_won": is_won or is_lost,
    }
    urls = {
        "lead_created": lead.get_absolute_url(),
        "assigned": lead.get_absolute_url(),
        "measurement": latest_mr.get_absolute_url() if latest_mr else None,
        "quotation": latest_q.get_absolute_url() if latest_q else None,
        "followup_won": lead.get_absolute_url(),
    }
    sublabels = {
        "lead_created": None,
        "assigned": lead.assigned_salesperson.get_full_name() or lead.assigned_salesperson.username
        if lead.assigned_salesperson_id else None,
        "measurement": latest_mr.get_status_display() if latest_mr else None,
        "quotation": f"{latest_q.root_number}-V{latest_q.version} · {latest_q.get_status_display()}"
        if latest_q else None,
        "followup_won": "Won" if is_won else ("Lost" if is_lost else None),
    }

    # A later stage being done implies every earlier one happened too, even if
    # (as with a few directly-created records) the specific field this checks
    # wasn't actually populated -- keeps the stepper from showing a "current"
    # bubble partway through an order that's actually long since finished.
    for i in range(len(PRE_ORDER_KEYS) - 1, 0, -1):
        if flags[PRE_ORDER_KEYS[i]]:
            for j in range(i):
                flags[PRE_ORDER_KEYS[j]] = True

    assignees = {
        "lead_created": None,
        "assigned": None,
        "measurement": _user_label(latest_mr.assigned_to) if latest_mr else None,
        "quotation": None,
        "followup_won": None,
    }

    stages_by_key = {}
    found_current = False
    for key in PRE_ORDER_KEYS:
        if flags[key]:
            state = "done"
        elif not found_current:
            state = "current"
            found_current = True
        else:
            state = "upcoming"
        stages_by_key[key] = _stage(key, dict(STAGE_DEFS)[key], state, urls[key], sublabels[key], assignees[key])

    banner = None
    service_badge = {"active": False, "label": "In Service"}

    if is_lost:
        lost_detail = getattr(lead, "lost_detail", None)
        reason = lost_detail.reason.name if lost_detail and lost_detail.reason_id else "No reason recorded"
        banner = {"type": "lost", "message": f"Lead Lost — {reason}"}
        for key in PRE_ORDER_KEYS:
            if key != "followup_won" and stages_by_key[key]["state"] != "done":
                stages_by_key[key]["state"] = "not_applicable"
        for key in POST_ORDER_KEYS:
            stages_by_key[key] = _stage(key, dict(STAGE_DEFS)[key], "not_applicable")
    else:
        order = getattr(lead, "order", None)
        if order is None:
            for key in POST_ORDER_KEYS:
                stages_by_key[key] = _stage(key, dict(STAGE_DEFS)[key], "upcoming")
        elif order.status == "cancelled":
            banner = {"type": "cancelled", "message": "Order Cancelled"}
            stages_by_key["order_confirmed"] = _stage(
                "order_confirmed", "Order Confirmed", "done", order.get_absolute_url(), order.order_number
            )
            for key in POST_ORDER_KEYS[1:]:
                stages_by_key[key] = _stage(key, dict(STAGE_DEFS)[key], "not_applicable")
        else:
            status_idx = ORDER_STATUS_SEQUENCE.index(order.status)
            stage_key_for_idx = [STATUS_TO_STAGE_KEY[s] for s in ORDER_STATUS_SEQUENCE]

            sheet = getattr(order, "production_sheet", None)
            qc = getattr(sheet, "quality_check", None) if sheet else None
            dispatch = getattr(order, "dispatch", None)
            installation = getattr(order, "installation", None)
            handover = getattr(order, "handover", None)
            final_measurement = order.final_measurements.order_by("-id").first()

            child = {
                "order_confirmed": (order.get_absolute_url(), order.order_number, _user_label(order.salesperson)),
                "final_measurement": (
                    final_measurement.get_absolute_url() if final_measurement else None,
                    final_measurement.get_status_display() if final_measurement else None,
                    _user_label(final_measurement.assigned_to) if final_measurement else None,
                ),
                "production": (
                    sheet.get_absolute_url() if sheet else None, sheet.get_status_display() if sheet else None,
                    _user_label(sheet.prepared_by) if sheet else None,
                ),
                "quality_check": (
                    reverse("production:qc_detail", args=[qc.pk]) if qc else None,
                    qc.get_status_display() if qc else None, _user_label(qc.checked_by) if qc else None,
                ),
                "dispatch": (
                    dispatch.get_absolute_url() if dispatch else None,
                    dispatch.get_status_display() if dispatch else None,
                    _user_label(dispatch.dispatched_by) if dispatch else None,
                ),
                "installation": (
                    installation.get_absolute_url() if installation else None,
                    installation.get_status_display() if installation else None,
                    _user_label(installation.team_leader) if installation else None,
                ),
                "handover": (
                    handover.get_absolute_url() if handover else None,
                    "Certificate generated" if handover else None,
                    _user_label(handover.company_representative) if handover else None,
                ),
            }

            for key in POST_ORDER_KEYS:
                first_idx = stage_key_for_idx.index(key)
                last_idx = len(stage_key_for_idx) - 1 - stage_key_for_idx[::-1].index(key)
                if order.status == "completed" and key == "handover":
                    state = "done"
                elif status_idx > last_idx:
                    state = "done"
                elif status_idx >= first_idx:
                    state = "current"
                else:
                    state = "upcoming"
                url, sublabel, assignee = child[key]
                stages_by_key[key] = _stage(key, dict(STAGE_DEFS)[key], state, url, sublabel, assignee)

            if order.status == "completed":
                service_badge = {"active": True, "label": "In Service"}

    stages = [stages_by_key[key] for key, _ in STAGE_DEFS]
    current_page_key = _current_page_key(obj)
    if current_page_key:
        for stage in stages:
            if stage["key"] == current_page_key:
                stage["is_current_page"] = True
                break

    return {
        "stages": stages, "banner": banner, "service_badge": service_badge,
        "customer_id": lead.customer.customer_code,
        "customer_name": lead.customer.customer_name,
        "quotation_number": latest_q.quotation_number if latest_q else None,
    }
