from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import Role, User

from . import guide as guide_content
from . import stages as stage_flow
from .context_processors import ALL_QUEUE_KEYS, _pending_counts, navigation
from .forms import (
    CafFinalForm,
    ChecklistForm,
    DispatchForm,
    FollowUpForm,
    LeadForm,
    LedgerForm,
    LostForm,
    MeasurementBoxForm,
    PaymentForm,
    ComplaintResolveForm,
    QuotationForm,
    RoughMeasurementForm,
    SalesTargetForm,
    ServiceComplaintForm,
    SingleFileForm,
    StageAccessForm,
    TaskForm,
    WonForm,
)
from .models import (
    FollowUp,
    Lead,
    LeadFile,
    Notification,
    Payment,
    ProductionRevision,
    SalesTarget,
    ServiceComplaint,
    Task,
)
from .pdf import render_caf, render_handover_certificate

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(request, *args, **kwargs):
            if not request.user.has_role(*roles):
                return HttpResponseForbidden("Your role does not have access to this page.")
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def sales_executives():
    """Everyone a lead can sit under — the Super Admin works leads of their own."""
    return User.objects.filter(role__in=[Role.SALESPERSON, Role.SUPER_ADMIN], is_active=True)


def visible_leads(user):
    """A salesperson sees only their own leads; every other role works the queue."""
    qs = Lead.objects.select_related("assigned_to")
    if user.role == Role.SALESPERSON:
        return qs.filter(assigned_to=user)
    return qs


def get_lead(request, pk):
    lead = get_object_or_404(Lead.objects.select_related("assigned_to"), pk=pk)
    if request.user.role == Role.SALESPERSON and lead.assigned_to_id != request.user.id:
        raise Http404
    return lead


def notify(lead, message, *roles):
    recipients = User.objects.filter(role__in=roles, is_active=True)
    Notification.objects.bulk_create(
        [Notification(user=user, lead=lead, message=message) for user in recipients]
    )


def notify_user(lead, message, user):
    if user:
        Notification.objects.create(user=user, lead=lead, message=message)


def safe_next(request, fallback):
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(target)
    return redirect(fallback)


def stage_redirect(lead, stage_key):
    return redirect(f"{lead.get_absolute_url()}?stage={stage_key}")


def guard_stage(request, lead, stage_key, check_role=True):
    """Both the role and the stage's turn are checked before any action runs.

    check_role=False is for the production sheet approval, which belongs to the
    measurement staff even though the stage itself is the production team's.
    """
    if check_role and not stage_flow.can_act(request.user, stage_key):
        return HttpResponseForbidden("Your role cannot act on this stage.")
    if stage_flow.current_stage_key(lead) != stage_key:
        messages.error(request, "That stage is not the active step for this lead.")
        return redirect(lead.get_absolute_url())
    return None


def save_upload(lead, kind, uploaded_file, user):
    return LeadFile.objects.create(lead=lead, kind=kind, file=uploaded_file, uploaded_by=user)


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------

def _queue_cards(user, counts):
    """The tiles a non-sales role sees on their dashboard."""
    by_role = {
        Role.MEASUREMENT: [
            ("Rough Measurements", "rough", "crm:queue_rough", "fa-ruler", "tone-navy"),
            ("Final Measurements", "final", "crm:queue_final", "fa-ruler-combined", "tone-violet"),
            ("Sheets to Validate", "validation", "crm:queue_production_validation", "fa-clipboard-check", "tone-amber"),
        ],
        Role.QUOTATION: [
            ("Quotations Pending", "quotation", "crm:queue_quotations", "fa-file-invoice", "tone-amber"),
        ],
        Role.PRODUCTION: [
            ("Sheets to Prepare", "production", "crm:queue_production", "fa-industry", "tone-navy"),
            ("On the Factory Floor", "fabrication", "crm:queue_fabrication", "fa-screwdriver-wrench", "tone-violet"),
        ],
        Role.FIELD_MANAGER: [
            ("Awaiting Handover", "warranty", "crm:queue_warranty", "fa-shield-halved", "tone-emerald"),
        ],
    }
    return [
        {"label": label, "count": counts.get(key, 0), "url": reverse(url), "icon": icon, "tone": tone}
        for label, key, url, icon, tone in by_role.get(user.role, [])
    ]


@login_required
def dashboard(request):
    today = timezone.localdate()
    # "Updates for the day" — only what was routed to this person's role.
    updates = request.user.notifications.filter(created_at__date=today, dismissed=False).select_related("lead")[:25]

    if request.user.role in (Role.SALESPERSON, Role.SUPER_ADMIN):
        return _sales_dashboard(request, updates)

    counts = _pending_counts(ALL_QUEUE_KEYS, request.user)
    return render(
        request,
        "crm/dashboard_queue.html",
        {
            "updates": updates,
            "cards": _queue_cards(request.user, counts),
            "my_todos": Task.objects.filter(assigned_to=request.user, done=False).select_related("assigned_by")[:8],
            "accounts_totals": _accounts_totals() if request.user.role == Role.ACCOUNTS else None,
        },
    )


def _sales_dashboard(request, updates):
    leads = visible_leads(request.user)
    selected_salesperson = request.GET.get("salesperson") or ""
    if request.user.is_super_admin and selected_salesperson:
        leads = leads.filter(assigned_to_id=selected_salesperson)

    today = timezone.localdate()
    month_start = today.replace(day=1)
    followups = FollowUp.objects.filter(lead__in=leads, done=False).select_related("lead")

    # The Super Admin's own panel lists their own leads, the same way a
    # salesperson's does; everyone else's overdue work is summarised beside it.
    # The figures across the top stay company-wide.
    panel_followups = followups
    overdue_by_person = None
    if request.user.is_super_admin and not selected_salesperson:
        panel_followups = followups.filter(lead__assigned_to=request.user)
        overdue_by_person = _overdue_by_person(today)

    context = {
        "lead_bank": leads.count(),
        "leads_this_month": leads.filter(created_at__date__gte=month_start).count(),
        "overdue_followups": followups.filter(date__lt=today).count(),
        "won_count": leads.filter(status=Lead.Status.WON).count(),
        "lost_count": leads.filter(status=Lead.Status.LOST).count(),
        "pending_quotations": leads.filter(status=Lead.Status.OPEN, quotation_uploaded_at__isnull=True).count(),
        # Every follow-up that is still open, whatever its date, until it is done.
        "open_followups": panel_followups,
        "today": today,
        "my_todos": Task.objects.filter(assigned_to=request.user, done=False).select_related("assigned_by")[:8],
        "salespeople": sales_executives(),
        "selected_salesperson": selected_salesperson,
        "overdue_by_person": overdue_by_person,
        "updates": updates,
    }
    return render(request, "crm/dashboard.html", context)


def _overdue_by_person(today):
    """How much overdue follow-up each sales executive is carrying."""
    rows = []
    for person in sales_executives():
        count = FollowUp.objects.filter(
            lead__assigned_to=person, done=False, date__lt=today
        ).count()
        rows.append({"person": person, "overdue": count})
    return sorted(rows, key=lambda row: -row["overdue"])


# ---------------------------------------------------------------------------
# leads
# ---------------------------------------------------------------------------


@role_required(Role.SALESPERSON)
def lead_list(request):
    leads = visible_leads(request.user)
    query = request.GET.get("q", "").strip()
    selected_salesperson = request.GET.get("salesperson") or ""
    if query:
        leads = leads.filter(
            Q(customer_name__icontains=query)
            | Q(phone__icontains=query)
            | Q(site_location__icontains=query)
            | Q(lead_number__icontains=query)
        )
    if request.user.is_super_admin and selected_salesperson:
        leads = leads.filter(assigned_to_id=selected_salesperson)

    status = request.GET.get("status") or ""
    if status == "won":
        leads = leads.filter(status=Lead.Status.WON)
    elif status == "lost":
        leads = leads.filter(status=Lead.Status.LOST)
    elif status == "followup":
        leads = leads.filter(status=Lead.Status.OPEN, quotation_uploaded_at__isnull=False)
    elif status == "overdue":
        leads = leads.filter(
            followups__done=False, followups__date__lt=timezone.localdate()
        ).distinct()

    return render(
        request,
        "crm/lead_list.html",
        {
            "leads": leads,
            "q": query,
            "salespeople": sales_executives(),
            "selected_salesperson": selected_salesperson,
            "status": status,
            "status_choices": [
                ("followup", "Follow-up stage"),
                ("won", "Won"),
                ("lost", "Lost"),
                ("overdue", "Overdue follow-up"),
            ],
        },
    )


@role_required(Role.SALESPERSON)
def lead_create(request):
    if request.method == "POST":
        form = LeadForm(request.POST, user=request.user)
        if form.is_valid():
            lead = form.save(commit=False)
            if request.user.role == Role.SALESPERSON:
                lead.assigned_to = request.user
            lead.created_by = request.user
            lead.save()
            if lead.assigned_to_id != request.user.id:
                notify_user(
                    lead,
                    f"A new lead opportunity has been assigned to you — {lead.customer_name}, {lead.site_location}",
                    lead.assigned_to,
                )
            messages.success(request, f"Lead {lead.lead_number} saved. Set the first follow-up below.")
            return redirect(lead.get_absolute_url())
    else:
        form = LeadForm(user=request.user)
    return render(request, "crm/lead_form.html", {"form": form})


@role_required(Role.SALESPERSON)
def lead_edit(request, pk):
    lead = get_lead(request, pk)
    was_assigned_to = lead.assigned_to_id
    if request.method == "POST":
        form = LeadForm(request.POST, instance=lead, user=request.user)
        if form.is_valid():
            lead = form.save()
            if lead.assigned_to_id != was_assigned_to:
                notify_user(
                    lead,
                    f"A new lead opportunity has been reassigned to you — {lead.customer_name}, {lead.site_location}",
                    lead.assigned_to,
                )
                messages.success(request, f"Lead updated and reassigned to {lead.assigned_to}.")
            else:
                messages.success(request, "Lead updated.")
            return redirect(lead.get_absolute_url())
    else:
        form = LeadForm(instance=lead, user=request.user)
    return render(request, "crm/lead_form.html", {"form": form, "lead": lead})


@role_required(Role.SALESPERSON)
@require_POST
def lead_delete(request, pk):
    lead = get_lead(request, pk)
    name = lead.customer_name
    lead.delete()
    messages.success(request, f"Lead for {name} deleted.")
    return redirect("crm:lead_list")


@login_required
def lead_detail(request, pk):
    lead = get_lead(request, pk)
    stage_list = stage_flow.build_stages(lead, request.user)
    if not stage_list:
        raise Http404

    # One stage on screen at a time. Default to whichever one needs work now;
    # if that is hidden from this person, show the latest step they can see
    # that has already been reached — usually the one they just finished.
    active_key = request.GET.get("stage")
    keys = [stage["key"] for stage in stage_list]
    if active_key not in keys:
        live = stage_flow.current_stage_key(lead)
        if live in keys:
            active_key = live
        else:
            order = stage_flow.ALL_STAGE_KEYS
            reached = order.index(live) if live else len(order)
            earlier = [key for key in keys if order.index(key) <= reached]
            active_key = earlier[-1] if earlier else keys[0]

    position = keys.index(active_key)
    context = {
        "lead": lead,
        "stages": stage_list,
        "stage": stage_list[position],
        "previous_stage": stage_list[position - 1] if position > 0 else None,
        "next_stage": stage_list[position + 1] if position + 1 < len(stage_list) else None,
        "current_stage": stage_flow.current_stage_key(lead),
        # Production is the one stage two roles touch: production uploads, measurement approves.
        "can_validate_production": request.user.has_role(Role.MEASUREMENT),
        "can_see_financials": stage_flow.can_see_financials(request.user),
        # Follow-ups run from the moment the lead exists, not just once a
        # quotation is out, so the scheduler shows on stage 1 as well.
        "can_follow_up": lead.status == Lead.Status.OPEN and request.user.has_role(Role.SALESPERSON),
        "measurement_form": MeasurementBoxForm(),
        "rough_form": RoughMeasurementForm(),
        "quotation_form": QuotationForm(),
        "caf_form": CafFinalForm(),
        "production_form": SingleFileForm(),
        "checklist_form": ChecklistForm(instance=lead),
        "dispatch_form": DispatchForm(instance=lead),
        "warranty_form": SingleFileForm(),
        "followup_form": FollowUpForm(),
    }
    return render(request, "crm/lead_detail.html", context)


# ---------------------------------------------------------------------------
# stage 1 — lead created (measurements box)
# ---------------------------------------------------------------------------


@role_required(Role.SALESPERSON)
@require_POST
def stage_measurements(request, pk):
    lead = get_lead(request, pk)
    blocked = guard_stage(request, lead, stage_flow.LEAD)
    if blocked:
        return blocked

    form = MeasurementBoxForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, form.errors.as_text())
        return stage_redirect(lead, stage_flow.LEAD)

    mode = form.cleaned_data["mode"]
    lead.measurement_mode = mode
    now = timezone.now()

    if mode == Lead.MeasurementMode.REQUESTED:
        lead.measurement_requested_at = now
        # Whatever map link came with the request stays on the lead, so the final
        # measurement visit later has it too.
        if form.cleaned_data.get("site_map_link"):
            lead.site_map_link = form.cleaned_data["site_map_link"]
        lead.save()
        notify(
            lead,
            f"Rough measurement needed — {lead.customer_name}, {lead.site_location} (site stage: {lead.get_site_stage_display()})",
            Role.MEASUREMENT,
        )
        messages.success(request, "Rough measurement request sent to the measurement team.")
    else:
        if form.cleaned_data.get("file"):
            save_upload(lead, LeadFile.Kind.ROUGH_MEASUREMENT, form.cleaned_data["file"], request.user)
        lead.measurement_notes = form.cleaned_data.get("notes", "")
        # Measurements already in hand, so the rough measurement stage is complete.
        lead.measurement_done_at = now
        lead.measurement_done_by = request.user
        lead.save()
        notify(lead, f"Measurements ready for quotation — {lead.customer_name}", Role.QUOTATION)
        messages.success(request, "Measurements saved. The quotation team has been notified.")
    return redirect(lead.get_absolute_url())


# ---------------------------------------------------------------------------
# stage 2 — rough measurement (measurement staff)
# ---------------------------------------------------------------------------


@role_required(Role.MEASUREMENT)
@require_POST
def stage_rough(request, pk):
    lead = get_lead(request, pk)
    blocked = guard_stage(request, lead, stage_flow.ROUGH)
    if blocked:
        return blocked

    form = RoughMeasurementForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, form.errors.as_text())
        return stage_redirect(lead, stage_flow.ROUGH)

    if form.cleaned_data.get("file"):
        save_upload(lead, LeadFile.Kind.ROUGH_MEASUREMENT, form.cleaned_data["file"], request.user)
    if form.cleaned_data.get("notes"):
        lead.measurement_notes = form.cleaned_data["notes"]
    lead.measurement_done_at = timezone.now()
    lead.measurement_done_by = request.user
    lead.save()
    notify(lead, f"Measurements ready for quotation — {lead.customer_name}", Role.QUOTATION)
    notify_user(lead, f"Rough measurement completed for {lead.customer_name}", lead.assigned_to)
    messages.success(request, "Rough measurement submitted.")
    return redirect(lead.get_absolute_url())


# ---------------------------------------------------------------------------
# stage 3 — quotation (accounts department)
# ---------------------------------------------------------------------------


@role_required(Role.QUOTATION)
@require_POST
def stage_quotation(request, pk):
    lead = get_lead(request, pk)
    blocked = guard_stage(request, lead, stage_flow.QUOTATION)
    if blocked:
        return blocked

    form = QuotationForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, form.errors.as_text())
        return stage_redirect(lead, stage_flow.QUOTATION)

    for uploaded in form.cleaned_data["files"]:
        save_upload(lead, LeadFile.Kind.QUOTATION, uploaded, request.user)
    save_upload(lead, LeadFile.Kind.ELEVATION, form.cleaned_data["elevation"], request.user)
    lead.quotation_number = form.cleaned_data["quotation_number"]
    lead.quotation_uploaded_at = timezone.now()
    lead.quotation_uploaded_by = request.user
    lead.save()
    notify_user(lead, f"Quotation {lead.quotation_number} uploaded for {lead.customer_name}", lead.assigned_to)
    messages.success(request, "Quotation uploaded and forwarded to the salesperson.")
    return redirect(lead.get_absolute_url())


# ---------------------------------------------------------------------------
# stage 4 — won / lost
# ---------------------------------------------------------------------------


@role_required(Role.SALESPERSON)
def stage_won(request, pk):
    lead = get_lead(request, pk)
    blocked = guard_stage(request, lead, stage_flow.DECISION)
    if blocked:
        return blocked

    if request.method == "POST":
        form = WonForm(request.POST, instance=lead)
        if form.is_valid():
            lead = form.save(commit=False)
            lead.status = Lead.Status.WON
            lead.won_at = timezone.now()
            lead.won_by = request.user
            lead.save()
            FollowUp.objects.filter(lead=lead, done=False).update(done=True, done_at=timezone.now())
            notify(
                lead,
                f"Order confirmed — {lead.customer_name}: value {lead.order_value}, advance {lead.advance_received}, balance {lead.balance_amount}",
                Role.ACCOUNTS,
            )
            notify(lead, f"CAF & final measurement pending — {lead.customer_name}", Role.MEASUREMENT)
            messages.success(request, "Order confirmed. Accounts and the measurement team have been notified.")
            return redirect(lead.get_absolute_url())
    else:
        form = WonForm(instance=lead)
    return render(request, "crm/won_form.html", {"lead": lead, "form": form})


@role_required(Role.SALESPERSON)
def stage_lost(request, pk):
    lead = get_lead(request, pk)
    blocked = guard_stage(request, lead, stage_flow.DECISION)
    if blocked:
        return blocked

    if request.method == "POST":
        form = LostForm(request.POST, instance=lead)
        if form.is_valid():
            lead = form.save(commit=False)
            lead.status = Lead.Status.LOST
            lead.lost_at = timezone.now()
            lead.lost_by = request.user
            lead.save()
            FollowUp.objects.filter(lead=lead, done=False).update(done=True, done_at=timezone.now())
            messages.info(request, "Lead marked as lost and moved to Lost Opportunities.")
            return redirect("crm:lost_opportunities")
    else:
        form = LostForm(instance=lead)
    return render(request, "crm/lost_form.html", {"lead": lead, "form": form})


# ---------------------------------------------------------------------------
# stage 5 — CAF & final measurement (measurement staff)
# ---------------------------------------------------------------------------


@role_required(Role.MEASUREMENT)
def caf_download(request, pk):
    lead = get_lead(request, pk)
    if lead.status != Lead.Status.WON:
        raise Http404
    return render_caf(lead)


@role_required(Role.MEASUREMENT)
@require_POST
def stage_caf_final(request, pk):
    lead = get_lead(request, pk)
    blocked = guard_stage(request, lead, stage_flow.CAF)
    if blocked:
        return blocked

    form = CafFinalForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, form.errors.as_text())
        return stage_redirect(lead, stage_flow.CAF)

    now = timezone.now()
    if form.cleaned_data.get("caf_signed"):
        save_upload(lead, LeadFile.Kind.CAF_SIGNED, form.cleaned_data["caf_signed"], request.user)
        lead.caf_signed_at = now
    if form.cleaned_data.get("final_measurement"):
        save_upload(lead, LeadFile.Kind.FINAL_MEASUREMENT, form.cleaned_data["final_measurement"], request.user)
        lead.final_measurement_at = now
    lead.caf_final_by = request.user
    lead.save()

    if lead.caf_signed_at and lead.final_measurement_at:
        notify(lead, f"Final measurement ready — production sheet needed for {lead.customer_name}", Role.PRODUCTION)
        messages.success(request, "Signed CAF and final measurement uploaded. Production has been notified.")
    else:
        pending = "final measurement file" if lead.caf_signed_at else "signed CAF"
        messages.warning(request, f"Uploaded. This stage completes once the {pending} is uploaded too.")
    return redirect(lead.get_absolute_url())


# ---------------------------------------------------------------------------
# stage 6 — production sheet
# ---------------------------------------------------------------------------


@role_required(Role.PRODUCTION)
@require_POST
def stage_production_sheet(request, pk):
    lead = get_lead(request, pk)
    blocked = guard_stage(request, lead, stage_flow.PRODUCTION)
    if blocked:
        return blocked

    form = SingleFileForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Choose the production sheet file to upload.")
        return stage_redirect(lead, stage_flow.PRODUCTION)

    # The superseded sheet goes, so nobody works from the wrong drawing.
    for stale in lead.production_sheet_files:
        stale.file.delete(save=False)
        stale.delete()
    save_upload(lead, LeadFile.Kind.PRODUCTION_SHEET, form.cleaned_data["file"], request.user)
    lead.production_sheet_at = timezone.now()
    lead.production_sheet_by = request.user
    lead.production_approved_at = None
    lead.production_approved_by = None
    lead.production_revision_note = ""
    lead.production_revision_at = None
    lead.save()
    notify(lead, f"Production sheet awaiting your approval — {lead.customer_name}", Role.MEASUREMENT)
    messages.success(request, "Production sheet uploaded. Waiting for measurement staff approval.")
    return redirect(lead.get_absolute_url())


@role_required(Role.MEASUREMENT)
@require_POST
def production_approve(request, pk):
    lead = get_lead(request, pk)
    blocked = guard_stage(request, lead, stage_flow.PRODUCTION, check_role=False)
    if blocked:
        return blocked
    if not lead.production_sheet_at:
        messages.error(request, "There is no production sheet to approve yet.")
        return redirect(lead.get_absolute_url())

    lead.production_approved_at = timezone.now()
    lead.production_approved_by = request.user
    lead.production_revision_note = ""
    lead.production_revision_at = None
    lead.save()
    notify(lead, f"Production sheet approved — {lead.customer_name}", Role.PRODUCTION)
    messages.success(request, "Production sheet approved.")
    return redirect(lead.get_absolute_url())


@role_required(Role.MEASUREMENT)
@require_POST
def production_need_revision(request, pk):
    lead = get_lead(request, pk)
    blocked = guard_stage(request, lead, stage_flow.PRODUCTION, check_role=False)
    if blocked:
        return blocked
    if not lead.production_sheet_at:
        messages.error(request, "There is no production sheet to send back yet.")
        return redirect(lead.get_absolute_url())

    remarks = request.POST.get("remarks", "").strip()
    if not remarks:
        messages.error(request, "Say what needs changing before sending the sheet back.")
        return stage_redirect(lead, stage_flow.PRODUCTION)

    lead.production_revision_note = remarks
    lead.production_revision_at = timezone.now()
    lead.save()
    ProductionRevision.objects.create(lead=lead, note=remarks, requested_by=request.user)
    notify(lead, f"Production sheet needs revision — {lead.customer_name}: {remarks}", Role.PRODUCTION)
    messages.success(request, "Sent back to the production team with your remarks.")
    return redirect(lead.get_absolute_url())


# ---------------------------------------------------------------------------
# stage 7 — site fabrication status
# ---------------------------------------------------------------------------


@role_required(Role.PRODUCTION)
@require_POST
def fabrication_start(request, pk):
    lead = get_lead(request, pk)
    blocked = guard_stage(request, lead, stage_flow.FABRICATION)
    if blocked:
        return blocked

    lead.fabrication_column = Lead.Fabrication.UNDER
    lead.save()
    messages.success(request, "Moved to Under Production.")
    return safe_next(request, lead.get_absolute_url())


@role_required(Role.PRODUCTION)
@require_POST
def fabrication_checklist(request, pk):
    lead = get_lead(request, pk)
    blocked = guard_stage(request, lead, stage_flow.FABRICATION)
    if blocked:
        return blocked

    form = ChecklistForm(request.POST, instance=lead)
    if not form.is_valid():
        return safe_next(request, lead.get_absolute_url())
    lead = form.save()

    # "Save checklist & move to dispatch" does both in one go — but only if
    # every step really is ticked; otherwise it saves and stays put.
    if request.POST.get("then_dispatch"):
        missing = _unfinished_steps(lead)
        if missing:
            messages.error(request, "Checklist saved, but these steps are still pending: " + ", ".join(missing) + ".")
            back = request.POST.get("back")
            if back and url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}):
                return redirect(back)
            return redirect(lead.get_absolute_url())
        lead.fabrication_column = Lead.Fabrication.READY
        lead.save()
        messages.success(request, f"Checklist saved and {lead.customer_name} moved to Ready for Dispatch.")
        return safe_next(request, lead.get_absolute_url())

    messages.success(request, "Checklist updated.")
    return safe_next(request, lead.get_absolute_url())


def _unfinished_steps(lead):
    return [lead._meta.get_field(field).verbose_name for field in Lead.CHECKLIST_FIELDS if not getattr(lead, field)]


@role_required(Role.PRODUCTION)
@require_POST
def fabrication_to_dispatch(request, pk):
    lead = get_lead(request, pk)
    blocked = guard_stage(request, lead, stage_flow.FABRICATION)
    if blocked:
        return blocked

    missing = _unfinished_steps(lead)
    if missing:
        messages.error(request, "Finish every step first — still pending: " + ", ".join(missing) + ".")
        return safe_next(request, lead.get_absolute_url())

    lead.fabrication_column = Lead.Fabrication.READY
    lead.save()
    messages.success(request, "Moved to Ready for Dispatch.")
    return safe_next(request, lead.get_absolute_url())


@role_required(Role.PRODUCTION)
def dispatch(request, pk):
    lead = get_lead(request, pk)
    blocked = guard_stage(request, lead, stage_flow.FABRICATION)
    if blocked:
        return blocked

    if request.method == "POST":
        form = DispatchForm(request.POST, instance=lead)
        if form.is_valid():
            lead = form.save(commit=False)
            lead.fabrication_column = Lead.Fabrication.DISPATCHED
            lead.dispatched_at = timezone.now()
            lead.dispatched_by = request.user
            lead.save()
            notify(lead, f"Dispatched — warranty & handover pending for {lead.customer_name}", Role.FIELD_MANAGER)
            messages.success(request, "Dispatched. Warranty & handover is now open for the field manager.")
            return safe_next(request, lead.get_absolute_url())
    else:
        form = DispatchForm(instance=lead)
    return render(
        request,
        "crm/dispatch_form.html",
        {"lead": lead, "form": form, "next": request.GET.get("next") or request.POST.get("next", "")},
    )


# ---------------------------------------------------------------------------
# stage 8 — warranty & handover (field manager)
# ---------------------------------------------------------------------------


@role_required(Role.FIELD_MANAGER)
def handover_download(request, pk):
    lead = get_lead(request, pk)
    if not lead.dispatched_at:
        raise Http404
    return render_handover_certificate(lead)


@role_required(Role.FIELD_MANAGER)
@require_POST
def handover_upload(request, pk):
    """The customer signs the handover certificate; the warranty is theirs to keep."""
    lead = get_lead(request, pk)
    blocked = guard_stage(request, lead, stage_flow.WARRANTY)
    if blocked:
        return blocked

    form = SingleFileForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Choose the signed handover certificate to upload.")
        return stage_redirect(lead, stage_flow.WARRANTY)

    save_upload(lead, LeadFile.Kind.HANDOVER_SIGNED, form.cleaned_data["file"], request.user)
    lead.handover_signed_at = timezone.now()
    lead.save()
    messages.success(request, "Signed handover certificate uploaded. You can now save the project.")
    return redirect(lead.get_absolute_url())


@role_required(Role.FIELD_MANAGER)
@require_POST
def project_save(request, pk):
    lead = get_lead(request, pk)
    blocked = guard_stage(request, lead, stage_flow.WARRANTY)
    if blocked:
        return blocked
    if not lead.handover_signed_at:
        messages.error(request, "Upload the signed handover certificate first.")
        return redirect(lead.get_absolute_url())

    lead.completed_at = timezone.now()
    lead.completed_by = request.user
    lead.save()
    notify_user(lead, f"Project completed — {lead.customer_name}", lead.assigned_to)
    messages.success(request, "Project saved and moved to Completed Projects.")
    return redirect("crm:queue_warranty")


# ---------------------------------------------------------------------------
# follow-ups
# ---------------------------------------------------------------------------


@role_required(Role.SALESPERSON)
def followups(request):
    leads = visible_leads(request.user)
    items = (
        FollowUp.objects.filter(lead__in=leads)
        .select_related("lead", "lead__assigned_to")
        # Still open first, oldest due date at the top.
        .order_by("done", "date", "time")
    )
    if request.GET.get("show") != "all":
        items = items.filter(done=False)
    return render(
        request,
        "crm/followups.html",
        {"followups": items, "show_all": request.GET.get("show") == "all", "today": timezone.localdate()},
    )


@role_required(Role.SALESPERSON)
@require_POST
def followup_add(request, pk):
    lead = get_lead(request, pk)
    if lead.status != Lead.Status.OPEN:
        messages.error(request, "This lead is already closed, so no more follow-ups can be scheduled.")
        return safe_next(request, lead.get_absolute_url())
    form = FollowUpForm(request.POST)
    if form.is_valid():
        # Only one follow-up runs at a time — scheduling the next closes the last.
        superseded = FollowUp.objects.filter(lead=lead, done=False).update(
            done=True, done_at=timezone.now(), superseded=True
        )
        followup = form.save(commit=False)
        followup.lead = lead
        followup.created_by = request.user
        followup.save()
        if superseded:
            messages.success(request, "Follow-up scheduled; the previous one moved to the history.")
        else:
            messages.success(request, "Follow-up scheduled.")
    else:
        messages.error(request, form.errors.as_text())
    return safe_next(request, lead.get_absolute_url())


@role_required(Role.SALESPERSON)
@require_POST
def followup_done(request, pk):
    followup = get_object_or_404(FollowUp.objects.select_related("lead"), pk=pk)
    if request.user.role == Role.SALESPERSON and followup.lead.assigned_to_id != request.user.id:
        raise Http404
    if not followup.can_be_completed:
        messages.error(request, "This lead is already closed, so its follow-ups are closed with it.")
        return safe_next(request, reverse("crm:followups"))
    followup.done = True
    followup.done_at = timezone.now()
    followup.save(update_fields=["done", "done_at"])
    return safe_next(request, reverse("crm:followups"))


# ---------------------------------------------------------------------------
# salesperson tabs
# ---------------------------------------------------------------------------


@role_required(Role.SALESPERSON)
def pipeline(request):
    leads = visible_leads(request.user)
    selected_salesperson = request.GET.get("salesperson") or ""
    if request.user.is_super_admin and selected_salesperson:
        leads = leads.filter(assigned_to_id=selected_salesperson)
    open_leads = leads.filter(status=Lead.Status.OPEN)
    quoted = open_leads.filter(quotation_uploaded_at__isnull=False)
    columns = [
        ("Quotation Pending", open_leads.filter(quotation_uploaded_at__isnull=True)),
        ("Quotation Sent", quoted.filter(followups__isnull=True).distinct()),
        ("Follow-up", quoted.filter(followups__isnull=False).distinct()),
        ("Won", leads.filter(status=Lead.Status.WON)),
        ("Lost", leads.filter(status=Lead.Status.LOST)),
    ]
    return render(
        request,
        "crm/pipeline.html",
        {
            "columns": columns,
            "salespeople": sales_executives(),
            "selected_salesperson": selected_salesperson,
        },
    )


@role_required(Role.SALESPERSON)
def targets(request):
    # Only the Super Admin sets targets; salespeople just see theirs.
    form = None
    if request.user.is_super_admin:
        if request.method == "POST":
            form = SalesTargetForm(request.POST)
            if form.is_valid():
                SalesTarget.objects.update_or_create(
                    salesperson=form.cleaned_data["salesperson"],
                    month=form.cleaned_data["month"].replace(day=1),
                    defaults={"amount": form.cleaned_data["amount"]},
                )
                messages.success(request, f"Target saved for {form.cleaned_data['salesperson']}.")
                return redirect("crm:targets")
        else:
            form = SalesTargetForm()
    elif request.method == "POST":
        return HttpResponseForbidden("Only the Super Admin can set sales targets.")

    target_qs = SalesTarget.objects.select_related("salesperson")
    if request.user.role == Role.SALESPERSON:
        target_qs = target_qs.filter(salesperson=request.user)

    # The Super Admin sees everyone's by default, and can pick one person to
    # read exactly as that person reads their own.
    selected_salesperson = request.GET.get("salesperson") or ""
    if request.user.is_super_admin and selected_salesperson:
        target_qs = target_qs.filter(salesperson_id=selected_salesperson)

    this_month = timezone.localdate().replace(day=1)
    current = target_qs.filter(month=this_month).first()
    won_this_month = []
    if current:
        won_this_month = Lead.objects.filter(
            assigned_to=current.salesperson,
            status=Lead.Status.WON,
            won_at__year=this_month.year,
            won_at__month=this_month.month,
        ).order_by("-won_at")
    return render(
        request,
        "crm/targets.html",
        {
            "form": form,
            "targets": target_qs,
            "current": current,
            "this_month": this_month,
            "won_this_month": won_this_month,
            "salespeople": sales_executives(),
            "selected_salesperson": selected_salesperson,
        },
    )


@role_required(Role.SALESPERSON)
def lost_opportunities(request):
    leads = visible_leads(request.user).filter(status=Lead.Status.LOST)
    return render(request, "crm/lost_list.html", {"leads": leads})


@role_required(Role.SALESPERSON)
def completed_projects(request):
    leads = visible_leads(request.user).filter(completed_at__isnull=False).prefetch_related("payments", "complaints")
    return render(request, "crm/completed_list.html", {"leads": leads})


# ---------------------------------------------------------------------------
# role queues
# ---------------------------------------------------------------------------


def _queue(request, template, leads, title, blurb):
    return render(request, template, {"leads": leads, "title": title, "blurb": blurb})


@role_required(Role.MEASUREMENT)
def queue_rough(request):
    leads = Lead.objects.filter(
        measurement_mode=Lead.MeasurementMode.REQUESTED, measurement_done_at__isnull=True, status=Lead.Status.OPEN
    ).select_related("assigned_to")
    return _queue(request, "crm/queues/simple.html", leads, "Rough Measurements", "Leads waiting for a rough measurement.")


@role_required(Role.MEASUREMENT)
def queue_final(request):
    leads = Lead.objects.filter(status=Lead.Status.WON).exclude(
        caf_signed_at__isnull=False, final_measurement_at__isnull=False
    ).select_related("assigned_to")
    return _queue(
        request,
        "crm/queues/simple.html",
        leads,
        "Final Measurements",
        "Confirmed orders waiting for the signed CAF and the final measurement.",
    )


@role_required(Role.MEASUREMENT)
def queue_production_validation(request):
    leads = Lead.objects.filter(
        production_sheet_at__isnull=False, production_approved_at__isnull=True
    ).select_related("assigned_to")
    return _queue(
        request,
        "crm/queues/simple.html",
        leads,
        "Production Sheet Validation",
        "Production sheets waiting for your approval.",
    )


@role_required(Role.QUOTATION)
def queue_quotations(request):
    leads = Lead.objects.filter(
        status=Lead.Status.OPEN, measurement_done_at__isnull=False, quotation_uploaded_at__isnull=True
    ).select_related("assigned_to")
    return _queue(
        request,
        "crm/queues/simple.html",
        leads,
        "Quotation Upload",
        "Customers whose measurements are in and are waiting for a quotation.",
    )


def _accounts_totals():
    leads = Lead.objects.filter(status=Lead.Status.WON).prefetch_related("payments")
    totals = leads.aggregate(value=Sum("order_value"), advance=Sum("advance_received"))
    totals["outstanding"] = sum(
        (lead.balance_amount or Decimal("0")) for lead in leads if lead.is_outstanding
    )
    return totals


@role_required(Role.ACCOUNTS)
def queue_accounts(request):
    leads = Lead.objects.filter(status=Lead.Status.WON).select_related("assigned_to").prefetch_related("payments")
    return render(request, "crm/queues/accounts.html", {"leads": leads, "totals": _accounts_totals()})


@role_required(Role.ACCOUNTS)
def ledger(request, pk):
    """A confirmed order's payment ledger — post entries and correct the figures."""
    lead = get_object_or_404(Lead.objects.prefetch_related("payments"), pk=pk, status=Lead.Status.WON)
    payment_form = PaymentForm(lead=lead)
    ledger_form = LedgerForm(instance=lead)

    if request.method == "POST":
        if "save_figures" in request.POST:
            ledger_form = LedgerForm(request.POST, instance=lead)
            if ledger_form.is_valid():
                ledger_form.save()
                messages.success(request, "Order figures updated.")
                return redirect("crm:ledger", pk=lead.pk)
        else:
            payment_form = PaymentForm(request.POST, request.FILES, lead=lead)
            if payment_form.is_valid():
                payment = payment_form.save(commit=False)
                payment.lead = lead
                payment.recorded_by = request.user
                payment.save()
                messages.success(request, "Payment entry posted.")
                return redirect("crm:ledger", pk=lead.pk)

    # Running balance down the ledger, starting from the advance.
    running = lead.advance_received or Decimal("0")
    rows = [
        {
            "date": lead.won_at,
            "label": "Advance received on order confirmation",
            "amount": running,
            "balance": (lead.order_value or Decimal("0")) - running,
            "entry": None,
        }
    ]
    for payment in lead.payments.all():
        running += payment.amount
        rows.append(
            {
                "date": payment.paid_on,
                "label": payment.remarks or "Payment received",
                "amount": payment.amount,
                "balance": (lead.order_value or Decimal("0")) - running,
                "entry": payment,
            }
        )

    return render(
        request,
        "crm/queues/ledger.html",
        {"lead": lead, "rows": rows, "payment_form": payment_form, "ledger_form": ledger_form},
    )


@role_required(Role.ACCOUNTS)
@require_POST
def payment_delete(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    lead_pk = payment.lead_id
    payment.delete()
    messages.success(request, "Payment entry removed.")
    return redirect("crm:ledger", pk=lead_pk)


@role_required(Role.PRODUCTION)
def queue_production(request):
    leads = Lead.objects.filter(
        caf_signed_at__isnull=False, final_measurement_at__isnull=False, production_approved_at__isnull=True
    ).select_related("assigned_to")
    return _queue(
        request, "crm/queues/simple.html", leads, "Production", "Orders waiting for a production sheet."
    )


FABRICATION_COLUMNS = [
    (Lead.Fabrication.FUTURE, "Future Production"),
    (Lead.Fabrication.UNDER, "Under Production"),
    (Lead.Fabrication.READY, "Ready for Dispatch"),
]


@role_required(Role.PRODUCTION)
def queue_fabrication(request):
    on_floor = Lead.objects.filter(status=Lead.Status.WON, dispatched_at__isnull=True).select_related("assigned_to")
    if request.user.is_super_admin:
        return _fabrication_admin(request, on_floor)
    return render(request, "crm/queues/fabrication_list.html", {"leads": on_floor})


def _fabrication_admin(request, on_floor):
    """The Super Admin's own way to push orders through, one column at a time."""
    keys = [key for key, _ in FABRICATION_COLUMNS]
    column = request.GET.get("column")
    if column not in keys:
        column = Lead.Fabrication.FUTURE
    return render(
        request,
        "crm/queues/fabrication_admin.html",
        {
            "column": column,
            "column_label": dict(FABRICATION_COLUMNS)[column],
            "columns": [
                (key, label, on_floor.filter(fabrication_column=key).count()) for key, label in FABRICATION_COLUMNS
            ],
            "leads": on_floor.filter(fabrication_column=column),
            "totals": _fabrication_totals(on_floor),
        },
    )


def _fabrication_totals(on_floor):
    """Each column written out in full, with its own totals underneath."""
    sections = []
    for key, label in FABRICATION_COLUMNS:
        column = on_floor.filter(fabrication_column=key)
        sections.append({
            "label": label,
            "key": key,
            "leads": column,
            "totals": _totals_for(column),
        })
    sections.append({
        "label": "All on the floor",
        "key": "all",
        "leads": None,
        "totals": _totals_for(on_floor),
    })
    return sections


def _totals_for(queryset):
    figures = queryset.aggregate(
        orders=Count("id"),
        windows=Sum("window_count"),
        sqft=Sum("total_sqft"),
        value=Sum("order_value"),
        advance=Sum("advance_received"),
    )
    value = figures["value"] or Decimal("0")
    advance = figures["advance"] or Decimal("0")
    return {
        "orders": figures["orders"] or 0,
        "windows": figures["windows"] or 0,
        "sqft": figures["sqft"] or 0,
        "value": value,
        "advance": advance,
        "balance": value - advance,
    }


@role_required(Role.PRODUCTION)
def fabrication_checklist_page(request, pk):
    lead = get_object_or_404(Lead, pk=pk, status=Lead.Status.WON, fabrication_column=Lead.Fabrication.UNDER)
    return render(request, "crm/queues/fabrication_checklist.html", {"lead": lead})


@role_required(Role.PRODUCTION)
def fabrication_detail(request, pk):
    lead = get_object_or_404(Lead, pk=pk, status=Lead.Status.WON)
    # The board is readable from the moment an order is won, but nothing can be
    # moved along until the measurement and production steps before it are done.
    return render(
        request,
        "crm/queues/fabrication_board.html",
        {
            "lead": lead,
            "checklist_form": ChecklistForm(instance=lead),
            "unlocked": lead.production_approved_at is not None,
            "waiting_on": _fabrication_waiting_on(lead),
        },
    )


def _fabrication_waiting_on(lead):
    if not (lead.caf_signed_at and lead.final_measurement_at):
        return "the measurement staff to upload the signed CAF and final measurement"
    if not lead.production_sheet_at:
        return "the production team to upload the production sheet"
    if not lead.production_approved_at:
        return "the measurement staff to approve the production sheet"
    return None


@role_required(Role.FIELD_MANAGER)
def queue_warranty(request):
    leads = Lead.objects.filter(dispatched_at__isnull=False, completed_at__isnull=True).select_related("assigned_to")
    return _queue(
        request,
        "crm/queues/simple.html",
        leads,
        "Warranty & Handover",
        "Dispatched orders waiting for the signed warranty certificate.",
    )


# ---------------------------------------------------------------------------
# notifications
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# to-do list (every role)
# ---------------------------------------------------------------------------


@login_required
def todo_list(request):
    mine = Task.objects.filter(assigned_to=request.user).select_related("assigned_by")
    if request.GET.get("show") != "all":
        mine = mine.filter(done=False)

    if request.method == "POST":
        form = TaskForm(request.POST, user=request.user)
        if form.is_valid():
            task = form.save(commit=False)
            task.assigned_by = request.user
            task.save()
            if task.assigned_to_id != request.user.id:
                Notification.objects.create(
                    user=task.assigned_to,
                    lead=None,
                    message=f"{request.user.get_full_name() or request.user.username} assigned you: {task.title}",
                )
            messages.success(request, f"To-do assigned to {task.assigned_to}.")
            return redirect("crm:todo_list")
    else:
        form = TaskForm(user=request.user)

    return render(
        request,
        "crm/todo_list.html",
        {
            "tasks": mine,
            "form": form,
            "assigned_by_me": Task.objects.filter(assigned_by=request.user, done=False)
            .exclude(assigned_to=request.user)
            .select_related("assigned_to"),
            "show_all": request.GET.get("show") == "all",
            "today": timezone.localdate(),
        },
    )


@login_required
@require_POST
def todo_done(request, pk):
    task = get_object_or_404(Task, pk=pk, assigned_to=request.user)
    task.done = True
    task.done_at = timezone.now()
    task.save(update_fields=["done", "done_at"])
    if task.assigned_by_id and task.assigned_by_id != request.user.id:
        Notification.objects.create(
            user=task.assigned_by,
            lead=None,
            message=f"{request.user.get_full_name() or request.user.username} completed: {task.title}",
        )
    return safe_next(request, reverse("crm:todo_list"))


@login_required
@require_POST
def todo_delete(request, pk):
    task = get_object_or_404(Task, pk=pk, assigned_by=request.user)
    task.delete()
    messages.success(request, "To-do removed.")
    return redirect("crm:todo_list")


# ---------------------------------------------------------------------------
# service complaints (after handover)
# ---------------------------------------------------------------------------


@role_required(Role.SALESPERSON, Role.FIELD_MANAGER)
@require_POST
def complaint_create(request, pk):
    """Raised against a finished project when the customer calls back."""
    lead = get_lead(request, pk)
    if not lead.completed_at:
        messages.error(request, "A complaint can only be raised once the project is handed over.")
        return redirect("crm:completed_projects")

    form = ServiceComplaintForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Describe what needs fixing.")
        return safe_next(request, reverse("crm:completed_projects"))

    complaint = form.save(commit=False)
    complaint.lead = lead
    complaint.raised_by = request.user
    complaint.save()
    notify(lead, f"Service complaint raised - {lead.customer_name}", Role.FIELD_MANAGER, Role.SUPER_ADMIN)
    messages.success(request, "Service complaint registered.")
    return safe_next(request, reverse("crm:completed_projects"))


@role_required(Role.FIELD_MANAGER)
def complaint_list(request):
    complaints = ServiceComplaint.objects.select_related("lead", "raised_by", "resolved_by")
    if request.GET.get("show") != "all":
        complaints = complaints.filter(resolved_at__isnull=True)
    return render(
        request,
        "crm/complaints.html",
        {
            "complaints": complaints,
            "show_all": request.GET.get("show") == "all",
            "form": ComplaintResolveForm(),
            "completed_leads": Lead.objects.filter(completed_at__isnull=False).order_by("customer_name"),
        },
    )


@role_required(Role.FIELD_MANAGER)
@require_POST
def complaint_resolve(request, pk):
    complaint = get_object_or_404(ServiceComplaint, pk=pk)
    complaint.resolution_note = request.POST.get("resolution_note", "").strip()
    complaint.resolved_at = timezone.now()
    complaint.resolved_by = request.user
    complaint.save()
    notify_user(complaint.lead, f"Service complaint resolved - {complaint.lead.customer_name}", complaint.raised_by)
    messages.success(request, "Marked as resolved.")
    return redirect("crm:complaint_list")


@role_required()  # no roles listed means Super Admin only
def stage_access_list(request):
    employees = User.objects.exclude(role=Role.SUPER_ADMIN).filter(is_active=True)
    rows = [
        {
            "employee": employee,
            "stages": [stage_flow.STAGE_LABELS[key] for key in stage_flow.visible_stage_keys(employee)],
            "is_custom": bool(employee.visible_stages),
        }
        for employee in employees
    ]
    return render(request, "crm/settings_stage_access.html", {"rows": rows})


@role_required()  # no roles listed means Super Admin only
def stage_access_edit(request, pk):
    employee = get_object_or_404(User, pk=pk)
    choices = [(key, stage_flow.STAGE_LABELS[key]) for key in stage_flow.ALL_STAGE_KEYS]
    if request.method == "POST":
        form = StageAccessForm(request.POST, stage_choices=choices)
        if form.is_valid():
            employee.visible_stages = form.cleaned_data["stages"]
            employee.save(update_fields=["visible_stages"])
            messages.success(request, f"Stage access updated for {employee}.")
            return redirect("crm:stage_access_list")
    else:
        form = StageAccessForm(initial={"stages": employee.visible_stages}, stage_choices=choices)
    return render(
        request,
        "crm/settings_stage_access_form.html",
        {
            "form": form,
            "employee": employee,
            "defaults": [stage_flow.STAGE_LABELS[key] for key in stage_flow.DEFAULT_ROLE_STAGES.get(employee.role, [])],
        },
    )


@login_required
@require_POST
def update_dismiss(request, pk):
    note = get_object_or_404(Notification, pk=pk, user=request.user)
    note.dismissed = True
    note.read = True
    note.save(update_fields=["dismissed", "read"])
    return safe_next(request, reverse("crm:dashboard"))


@login_required
def notifications(request):
    items = request.user.notifications.select_related("lead")[:100]
    request.user.notifications.filter(read=False).update(read=True)
    return render(request, "crm/notifications.html", {"notifications": items})


# ---------------------------------------------------------------------------
# walkthrough
# ---------------------------------------------------------------------------


def _guide_context(request):
    """The intro scenes and the tour, both built for whoever is signed in."""
    nav_groups = navigation(request).get("nav_groups", [])
    return {
        "intro": guide_content.intro_for(request.user),
        "tour_steps": guide_content.tour_for(nav_groups),
        "written": guide_content.written_guide(nav_groups),
    }


@login_required
def guide(request):
    return render(request, "crm/guide.html", _guide_context(request))


@login_required
@require_POST
def guide_seen(request):
    """Records that the intro, the tour, or both have been got through.

    Sent when the walkthrough is finished and when it is skipped, so it plays
    once and once only. It is never unset — the Guide tab replays on demand.
    """
    now = timezone.now()
    fields = []
    if request.POST.get("intro") and request.user.intro_seen_at is None:
        request.user.intro_seen_at = now
        fields.append("intro_seen_at")
    if request.POST.get("tour") and request.user.tour_seen_at is None:
        request.user.tour_seen_at = now
        fields.append("tour_seen_at")
    if fields:
        request.user.save(update_fields=fields)
    return JsonResponse({"ok": True})
