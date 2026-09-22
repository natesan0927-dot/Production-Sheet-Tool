from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import Role, User

from . import stages as stage_flow
from .forms import (
    CafFinalForm,
    ChecklistForm,
    DispatchForm,
    FabricationDetailsForm,
    FollowUpForm,
    LeadForm,
    LostForm,
    MeasurementBoxForm,
    QuotationForm,
    RoughMeasurementForm,
    SalesTargetForm,
    SingleFileForm,
    WonForm,
)
from .models import FollowUp, Lead, LeadFile, Notification, SalesTarget
from .pdf import render_caf, render_warranty_certificate

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


def stage_redirect(lead, stage_key):
    return redirect(f"{lead.get_absolute_url()}#stage-{stage_key}")


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

ROLE_LANDING = {
    Role.MEASUREMENT: "crm:queue_rough",
    Role.ACCOUNTS: "crm:queue_quotations",
    Role.PRODUCTION: "crm:queue_production",
    Role.FIELD_MANAGER: "crm:queue_warranty",
}


@login_required
def dashboard(request):
    landing = ROLE_LANDING.get(request.user.role)
    if landing:
        return redirect(landing)

    leads = visible_leads(request.user)
    selected_salesperson = request.GET.get("salesperson") or ""
    if request.user.is_super_admin and selected_salesperson:
        leads = leads.filter(assigned_to_id=selected_salesperson)

    today = timezone.localdate()
    month_start = today.replace(day=1)
    followups = FollowUp.objects.filter(lead__in=leads, done=False).select_related("lead")

    # "To do for the day": today's follow-ups plus leads sitting on this
    # salesperson's own step of the journey.
    todo_labels = {
        stage_flow.LEAD: "Add the measurements to move this forward",
        stage_flow.DECISION: "Quotation is ready — mark it won or lost",
    }
    todo_leads = []
    for lead in leads.filter(status=Lead.Status.OPEN):
        label = todo_labels.get(stage_flow.current_stage_key(lead))
        if label:
            todo_leads.append({"lead": lead, "label": label})

    context = {
        "lead_bank": leads.count(),
        "leads_this_month": leads.filter(created_at__date__gte=month_start).count(),
        "overdue_followups": followups.filter(date__lt=today).count(),
        "won_count": leads.filter(status=Lead.Status.WON).count(),
        "lost_count": leads.filter(status=Lead.Status.LOST).count(),
        "pending_quotations": leads.filter(status=Lead.Status.OPEN, quotation_uploaded_at__isnull=True).count(),
        "today_followups": followups.filter(date=today),
        "todo_leads": todo_leads,
        "salespeople": User.objects.filter(role=Role.SALESPERSON, is_active=True),
        "selected_salesperson": selected_salesperson,
    }
    return render(request, "crm/dashboard.html", context)


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
    return render(
        request,
        "crm/lead_list.html",
        {
            "leads": leads,
            "q": query,
            "salespeople": User.objects.filter(role=Role.SALESPERSON, is_active=True),
            "selected_salesperson": selected_salesperson,
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
            messages.success(request, f"Lead {lead.lead_number} saved.")
            return redirect(lead.get_absolute_url())
    else:
        form = LeadForm(user=request.user)
    return render(request, "crm/lead_form.html", {"form": form})


@role_required()  # no roles listed means Super Admin only
def lead_edit(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    if request.method == "POST":
        form = LeadForm(request.POST, instance=lead, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Lead updated.")
            return redirect(lead.get_absolute_url())
    else:
        form = LeadForm(instance=lead, user=request.user)
    return render(request, "crm/lead_form.html", {"form": form, "lead": lead})


@login_required
def lead_detail(request, pk):
    lead = get_lead(request, pk)
    stage_list = stage_flow.build_stages(lead, request.user)
    context = {
        "lead": lead,
        "stages": stage_list,
        "current_stage": stage_flow.current_stage_key(lead),
        # Production is the one stage two roles touch: production uploads, measurement approves.
        "can_validate_production": request.user.has_role(Role.MEASUREMENT),
        "measurement_form": MeasurementBoxForm(),
        "rough_form": RoughMeasurementForm(),
        "quotation_form": QuotationForm(),
        "caf_form": CafFinalForm(),
        "production_form": SingleFileForm(),
        "fabrication_form": FabricationDetailsForm(instance=lead),
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
        notify(lead, f"Measurements ready for quotation — {lead.customer_name}", Role.ACCOUNTS)
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
    notify(lead, f"Measurements ready for quotation — {lead.customer_name}", Role.ACCOUNTS)
    notify_user(lead, f"Rough measurement completed for {lead.customer_name}", lead.assigned_to)
    messages.success(request, "Rough measurement submitted.")
    return redirect(lead.get_absolute_url())


# ---------------------------------------------------------------------------
# stage 3 — quotation (accounts department)
# ---------------------------------------------------------------------------


@role_required(Role.ACCOUNTS)
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
            lead.in_negotiation = False
            lead.save()
            FollowUp.objects.filter(lead=lead, done=False).update(done=True)
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
            lead.in_negotiation = False
            lead.save()
            FollowUp.objects.filter(lead=lead, done=False).update(done=True)
            messages.info(request, "Lead marked as lost and moved to Lost Opportunities.")
            return redirect("crm:lost_opportunities")
    else:
        form = LostForm(instance=lead)
    return render(request, "crm/lost_form.html", {"lead": lead, "form": form})


@role_required(Role.SALESPERSON)
@require_POST
def toggle_negotiation(request, pk):
    lead = get_lead(request, pk)
    lead.in_negotiation = not lead.in_negotiation
    lead.save(update_fields=["in_negotiation", "updated_at"])
    return redirect(lead.get_absolute_url())


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

    save_upload(lead, LeadFile.Kind.PRODUCTION_SHEET, form.cleaned_data["file"], request.user)
    lead.production_sheet_at = timezone.now()
    lead.production_sheet_by = request.user
    lead.production_approved_at = None
    lead.production_approved_by = None
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
    lead.save()
    notify(lead, f"Production sheet approved — {lead.customer_name}", Role.PRODUCTION)
    messages.success(request, "Production sheet approved.")
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

    form = FabricationDetailsForm(request.POST, instance=lead)
    if not form.is_valid():
        messages.error(request, "Fill in the window count, total sq ft and order value first.")
        return stage_redirect(lead, stage_flow.FABRICATION)

    lead = form.save(commit=False)
    lead.fabrication_column = Lead.Fabrication.UNDER
    lead.save()
    messages.success(request, "Moved to Under Production.")
    return redirect(request.POST.get("next") or lead.get_absolute_url())


@role_required(Role.PRODUCTION)
@require_POST
def fabrication_checklist(request, pk):
    lead = get_lead(request, pk)
    blocked = guard_stage(request, lead, stage_flow.FABRICATION)
    if blocked:
        return blocked

    form = ChecklistForm(request.POST, instance=lead)
    if form.is_valid():
        form.save()
        messages.success(request, "Checklist updated.")
    return redirect(request.POST.get("next") or lead.get_absolute_url())


@role_required(Role.PRODUCTION)
@require_POST
def fabrication_to_dispatch(request, pk):
    lead = get_lead(request, pk)
    blocked = guard_stage(request, lead, stage_flow.FABRICATION)
    if blocked:
        return blocked

    lead.fabrication_column = Lead.Fabrication.READY
    lead.save()
    messages.success(request, "Moved to Ready for Dispatch.")
    return redirect(request.POST.get("next") or lead.get_absolute_url())


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
            lead.save()
            notify(lead, f"Dispatched — warranty & handover pending for {lead.customer_name}", Role.FIELD_MANAGER)
            messages.success(request, "Dispatched. Warranty & handover is now open for the field manager.")
            return redirect(lead.get_absolute_url())
    else:
        form = DispatchForm(instance=lead)
    return render(request, "crm/dispatch_form.html", {"lead": lead, "form": form})


# ---------------------------------------------------------------------------
# stage 8 — warranty & handover (field manager)
# ---------------------------------------------------------------------------


@role_required(Role.FIELD_MANAGER)
def warranty_download(request, pk):
    lead = get_lead(request, pk)
    if not lead.dispatched_at:
        raise Http404
    return render_warranty_certificate(lead)


@role_required(Role.FIELD_MANAGER)
@require_POST
def warranty_upload(request, pk):
    lead = get_lead(request, pk)
    blocked = guard_stage(request, lead, stage_flow.WARRANTY)
    if blocked:
        return blocked

    form = SingleFileForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Choose the signed warranty certificate to upload.")
        return stage_redirect(lead, stage_flow.WARRANTY)

    save_upload(lead, LeadFile.Kind.WARRANTY_SIGNED, form.cleaned_data["file"], request.user)
    lead.warranty_signed_at = timezone.now()
    lead.save()
    messages.success(request, "Signed warranty certificate uploaded. You can now save the project.")
    return redirect(lead.get_absolute_url())


@role_required(Role.FIELD_MANAGER)
@require_POST
def project_save(request, pk):
    lead = get_lead(request, pk)
    blocked = guard_stage(request, lead, stage_flow.WARRANTY)
    if blocked:
        return blocked
    if not lead.warranty_signed_at:
        messages.error(request, "Upload the signed warranty certificate first.")
        return redirect(lead.get_absolute_url())

    lead.completed_at = timezone.now()
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
    items = FollowUp.objects.filter(lead__in=leads).select_related("lead", "lead__assigned_to")
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
    form = FollowUpForm(request.POST)
    if form.is_valid():
        followup = form.save(commit=False)
        followup.lead = lead
        followup.created_by = request.user
        followup.save()
        messages.success(request, "Follow-up scheduled.")
    else:
        messages.error(request, form.errors.as_text())
    return redirect(request.POST.get("next") or lead.get_absolute_url())


@role_required(Role.SALESPERSON)
@require_POST
def followup_done(request, pk):
    followup = get_object_or_404(FollowUp.objects.select_related("lead"), pk=pk)
    if request.user.role == Role.SALESPERSON and followup.lead.assigned_to_id != request.user.id:
        raise Http404
    followup.done = True
    followup.save(update_fields=["done"])
    return redirect(request.POST.get("next") or "crm:followups")


# ---------------------------------------------------------------------------
# salesperson tabs
# ---------------------------------------------------------------------------


@role_required(Role.SALESPERSON)
def pipeline(request):
    leads = visible_leads(request.user)
    open_leads = leads.filter(status=Lead.Status.OPEN)
    quoted = open_leads.filter(quotation_uploaded_at__isnull=False)
    columns = [
        ("Quotation Pending", open_leads.filter(quotation_uploaded_at__isnull=True)),
        ("Quotation Sent", quoted.filter(in_negotiation=False, followups__isnull=True).distinct()),
        ("Follow-up", quoted.filter(in_negotiation=False, followups__isnull=False).distinct()),
        ("Negotiation", quoted.filter(in_negotiation=True)),
        ("Won", leads.filter(status=Lead.Status.WON)),
        ("Lost", leads.filter(status=Lead.Status.LOST)),
    ]
    return render(request, "crm/pipeline.html", {"columns": columns})


@role_required(Role.SALESPERSON)
def targets(request):
    if request.method == "POST":
        form = SalesTargetForm(request.POST, user=request.user)
        if form.is_valid():
            salesperson = request.user if request.user.role == Role.SALESPERSON else form.cleaned_data["salesperson"]
            SalesTarget.objects.update_or_create(
                salesperson=salesperson,
                month=form.cleaned_data["month"].replace(day=1),
                defaults={"amount": form.cleaned_data["amount"]},
            )
            messages.success(request, "Target saved.")
            return redirect("crm:targets")
    else:
        form = SalesTargetForm(user=request.user)

    target_qs = SalesTarget.objects.select_related("salesperson")
    if request.user.role == Role.SALESPERSON:
        target_qs = target_qs.filter(salesperson=request.user)

    this_month = timezone.localdate().replace(day=1)
    current = target_qs.filter(month=this_month).first()
    return render(
        request,
        "crm/targets.html",
        {"form": form, "targets": target_qs, "current": current, "this_month": this_month},
    )


@role_required(Role.SALESPERSON)
def lost_opportunities(request):
    leads = visible_leads(request.user).filter(status=Lead.Status.LOST)
    return render(request, "crm/lost_list.html", {"leads": leads})


@role_required(Role.SALESPERSON)
def completed_projects(request):
    leads = visible_leads(request.user).filter(completed_at__isnull=False)
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


@role_required(Role.ACCOUNTS)
def queue_quotations(request):
    leads = Lead.objects.filter(
        status=Lead.Status.OPEN, measurement_done_at__isnull=False, quotation_uploaded_at__isnull=True
    ).select_related("assigned_to")
    return _queue(
        request, "crm/queues/simple.html", leads, "Quotations", "Measurements received — waiting for a quotation."
    )


@role_required(Role.ACCOUNTS)
def queue_accounts(request):
    leads = Lead.objects.filter(status=Lead.Status.WON).select_related("assigned_to")
    totals = leads.aggregate(value=Sum("order_value"), advance=Sum("advance_received"))
    return render(request, "crm/queues/accounts.html", {"leads": leads, "totals": totals})


@role_required(Role.PRODUCTION)
def queue_production(request):
    leads = Lead.objects.filter(
        caf_signed_at__isnull=False, final_measurement_at__isnull=False, production_approved_at__isnull=True
    ).select_related("assigned_to")
    return _queue(
        request, "crm/queues/simple.html", leads, "Production", "Orders waiting for a production sheet."
    )


@role_required(Role.PRODUCTION)
def queue_fabrication(request):
    leads = Lead.objects.filter(production_approved_at__isnull=False, dispatched_at__isnull=True)
    columns = [
        (Lead.Fabrication.FUTURE, "Future Production", leads.filter(fabrication_column=Lead.Fabrication.FUTURE)),
        (Lead.Fabrication.UNDER, "Under Production", leads.filter(fabrication_column=Lead.Fabrication.UNDER)),
        (Lead.Fabrication.READY, "Ready for Dispatch", leads.filter(fabrication_column=Lead.Fabrication.READY)),
    ]
    return render(request, "crm/queues/fabrication.html", {"columns": columns})


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


@login_required
def notifications(request):
    items = request.user.notifications.select_related("lead")[:100]
    request.user.notifications.filter(read=False).update(read=True)
    return render(request, "crm/notifications.html", {"notifications": items})
