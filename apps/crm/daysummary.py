"""What each person actually did on a given day.

Every line comes from a field that already records who did the work and when,
so nothing here is inferred — if the software cannot say who did something, it
is left out rather than guessed at.
"""

from django.db.models import Sum

from apps.accounts.models import Role

from .models import (
    FollowUp,
    InstallerPayment,
    InvoiceCharge,
    Lead,
    LeadAssignment,
    Payment,
    ProductionRevision,
    QuotationRevision,
    ServiceComplaint,
    Task,
)
from .templatetags.money import rupees


def _leads(field, user, stamp, day):
    return (
        Lead.objects.filter(**{field: user, f"{stamp}__date": day})
        .select_related("assigned_to")
        .order_by("-" + stamp)
    )


def _section(title, icon, rows, value=None):
    return {"title": title, "icon": icon, "rows": list(rows), "value": value}


def _lead_rows(queryset, note=None):
    return [
        {
            "lead": lead,
            "label": lead.customer_name,
            "detail": lead.site_location,
            "note": note(lead) if note else "",
        }
        for lead in queryset
    ]


def sales_sections(user, day):
    created = _leads("created_by", user, "created_at", day)
    requested = _leads("measurement_requested_by", user, "measurement_requested_at", day)
    won = _leads("won_by", user, "won_at", day)
    lost = _leads("lost_by", user, "lost_at", day)
    booked = FollowUp.objects.filter(created_by=user, created_at__date=day).select_related("lead")
    # Worked by this person: not rescheduled, not closed because the lead was won or lost.
    closed = FollowUp.objects.filter(
        lead__assigned_to=user, done=True, superseded=False, closed_with_lead=False, done_at__date=day
    ).select_related("lead")
    asked = QuotationRevision.objects.filter(requested_by=user, requested_at__date=day).select_related("lead")

    return [
        _section("Leads added", "fa-user-plus", _lead_rows(created)),
        _section("Rough measurements requested", "fa-ruler", _lead_rows(requested)),
        _section(
            "Orders won", "fa-trophy", _lead_rows(won, lambda lead: rupees(lead.order_value)),
            value=won.aggregate(total=Sum("order_value"))["total"],
        ),
        _section("Leads lost", "fa-circle-xmark", _lead_rows(lost, lambda lead: lead.lost_reason)),
        _section("Follow-ups booked", "fa-calendar-plus", [
            {"lead": f.lead, "label": f.lead.customer_name,
             "detail": f"{f.date:%d %b %Y} at {f.time:%H:%M}", "note": f.note}
            for f in booked
        ]),
        _section("Follow-ups completed", "fa-circle-check", [
            {"lead": f.lead, "label": f.lead.customer_name,
             "detail": f"due {f.date:%d %b %Y}", "note": f.note}
            for f in closed
        ]),
        _section("Quotation revisions requested", "fa-rotate-left", [
            {"lead": r.lead, "label": r.lead.customer_name, "detail": "", "note": r.note}
            for r in asked
        ]),
    ]


def measurement_sections(user, day):
    rough = _leads("measurement_done_by", user, "measurement_done_at", day)
    final = _leads("caf_final_by", user, "final_measurement_at", day)
    approved = _leads("production_approved_by", user, "production_approved_at", day)
    sent_back = ProductionRevision.objects.filter(
        requested_by=user, requested_at__date=day
    ).select_related("lead")

    return [
        _section("Rough measurements recorded", "fa-ruler", _lead_rows(rough)),
        _section("Signed CAF + final measurement uploaded", "fa-ruler-combined", _lead_rows(final)),
        _section("Production sheets approved", "fa-clipboard-check", _lead_rows(approved)),
        _section("Production sheets sent back", "fa-rotate-left", [
            {"lead": r.lead, "label": r.lead.customer_name, "detail": "", "note": r.note}
            for r in sent_back
        ]),
    ]


def quotation_sections(user, day):
    uploaded = _leads("quotation_uploaded_by", user, "quotation_uploaded_at", day)
    return [
        _section("Quotations uploaded", "fa-file-invoice",
                 _lead_rows(uploaded, lambda lead: lead.quotation_number)),
    ]


def accounts_sections(user, day):
    posted = Payment.objects.filter(recorded_by=user, created_at__date=day).select_related("lead")
    charged = InvoiceCharge.objects.filter(added_by=user, added_at__date=day).select_related("lead")
    paid_out = InstallerPayment.objects.filter(recorded_by=user, created_at__date=day).select_related("lead")
    return [
        _section(
            "Payments posted", "fa-indian-rupee-sign",
            [{"lead": p.lead, "label": p.lead.customer_name,
              "detail": rupees(p.amount), "note": p.remarks} for p in posted],
            value=posted.aggregate(total=Sum("amount"))["total"],
        ),
        _section(
            "Charges added to invoices", "fa-file-invoice-dollar",
            [{"lead": c.lead, "label": c.lead.customer_name,
              "detail": rupees(c.amount), "note": c.description} for c in charged],
            value=charged.aggregate(total=Sum("amount"))["total"],
        ),
        _section(
            "Paid to installers", "fa-helmet-safety",
            [{"lead": p.lead, "label": p.lead.customer_name,
              "detail": f"{rupees(p.amount)} to {p.lead.installation_person or 'the installer'}", "note": p.remarks}
             for p in paid_out],
            value=paid_out.aggregate(total=Sum("amount"))["total"],
        ),
    ]


def production_sections(user, day):
    sheets = _leads("production_sheet_by", user, "production_sheet_at", day)
    dispatched = _leads("dispatched_by", user, "dispatched_at", day)
    return [
        _section("Production sheets uploaded", "fa-industry", _lead_rows(sheets)),
        _section("Orders dispatched", "fa-truck",
                 _lead_rows(dispatched, lambda lead: lead.invoice_number)),
    ]


def field_sections(user, day):
    handed = _leads("handover_signed_by", user, "handover_signed_at", day)
    finished = _leads("completed_by", user, "completed_at", day)
    resolved = ServiceComplaint.objects.filter(
        resolved_by=user, resolved_at__date=day
    ).select_related("lead")
    return [
        _section("Signed handover certificates uploaded", "fa-file-signature", _lead_rows(handed)),
        _section("Projects completed", "fa-circle-check", _lead_rows(finished)),
        _section("Service requests resolved", "fa-screwdriver", [
            {"lead": c.lead, "label": c.lead.customer_name, "detail": "", "note": c.resolution_note}
            for c in resolved
        ]),
    ]


def admin_sections(user, day):
    """The Super Admin works every stage, so their day is everyone's put together."""
    sections = []
    for build in (sales_sections, measurement_sections, quotation_sections,
                  accounts_sections, production_sections, field_sections):
        sections.extend(build(user, day))
    moved = LeadAssignment.objects.filter(changed_by=user, changed_at__date=day).select_related(
        "lead", "from_user", "to_user"
    )
    sections.append(_section("Leads reassigned", "fa-people-arrows", [
        {"lead": a.lead, "label": a.lead.customer_name,
         "detail": f"{a.from_user or '—'} → {a.to_user or '—'}", "note": ""}
        for a in moved
    ]))
    return sections


ROLE_SECTIONS = {
    Role.SALESPERSON: sales_sections,
    Role.MEASUREMENT: measurement_sections,
    Role.QUOTATION: quotation_sections,
    Role.ACCOUNTS: accounts_sections,
    Role.PRODUCTION: production_sections,
    Role.FIELD_MANAGER: field_sections,
    Role.SUPER_ADMIN: admin_sections,
}


def shared_sections(user, day):
    """Work anyone does, whatever their role."""
    finished = Task.objects.filter(assigned_to=user, done=True, done_at__date=day).select_related("assigned_by")
    handed_out = Task.objects.filter(assigned_by=user, created_at__date=day).exclude(
        assigned_to=user
    ).select_related("assigned_to")
    raised = ServiceComplaint.objects.filter(raised_by=user, raised_at__date=day).select_related("lead")
    return [
        _section("To-dos completed", "fa-list-check", [
            {"lead": None, "label": t.title,
             "detail": f"from {t.assigned_by}" if t.assigned_by else "", "note": t.details}
            for t in finished
        ]),
        _section("To-dos assigned to others", "fa-share", [
            {"lead": None, "label": t.title, "detail": f"to {t.assigned_to}", "note": t.details}
            for t in handed_out
        ]),
        _section("Service requests raised", "fa-screwdriver-wrench", [
            {"lead": c.lead, "label": c.lead.customer_name, "detail": "", "note": c.description}
            for c in raised
        ]),
    ]


def for_person(user, day):
    """Every section with something in it, plus how many entries in total."""
    build = ROLE_SECTIONS.get(user.role, sales_sections)
    sections = [s for s in build(user, day) + shared_sections(user, day) if s["rows"]]
    return {
        "sections": sections,
        "total": sum(len(s["rows"]) for s in sections),
    }


def counts_for(people, day):
    """One number per person, for the list before you pick someone."""
    return [{"person": person, "total": for_person(person, day)["total"]} for person in people]
