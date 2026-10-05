from datetime import timedelta
from decimal import Decimal
from functools import wraps
from urllib.parse import quote, urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Exists, F, OuterRef, Q, Sum
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.utils.http import content_disposition_header, url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts import recovery
from apps.accounts.models import Role, User

from . import aging, daysummary, monthly, queues, storage_usage, updates
from . import guide as guide_content
from . import stages as stage_flow
from .context_processors import ALL_QUEUE_KEYS, _pending_counts, navigation
from .forms import (
    CafFinalForm,
    InvoiceChargeForm,
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
    FilesForm,
    StageAccessForm,
    TaskForm,
    WonForm,
    installation_total,
)
from .models import (
    FollowUp,
    Lead,
    LeadAssignment,
    LeadFile,
    Notification,
    Payment,
    PaymentReceipt,
    InvoiceCharge,
    ProductionRevision,
    QuotationRevision,
    SalesTarget,
    ServiceComplaint,
    Task,
    credited_q,
)
from .pdf import render_caf, render_handover_certificate, render_warranty_certificate
from .scan import ScanError, pages_to_pdf, pdf_filename
from .statements import render_customer_ledger, render_outstanding_statement
from .templatetags.money import rupees

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
    """The sales executives, for the filters and the per-person figures.

    The Super Admin only monitors and follows no leads. Anyone else still holding
    open leads — someone since removed, say — stays on the list, so those leads
    can be found and handed to someone else.
    """
    working = Q(role=Role.SALESPERSON, is_active=True)
    left_behind = Q(leads__status=Lead.Status.OPEN) & ~Q(role=Role.SALESPERSON, is_active=True)
    return User.objects.filter(working | left_behind).distinct()


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


def notify(lead, message, *roles, topic="", link=""):
    """An update for everyone in these roles. See updates.py for what topic does."""
    recipients = User.objects.filter(role__in=roles, is_active=True)
    updates.send(recipients, message, lead=lead, topic=topic, link=link)


def notify_user(lead, message, user, topic="", link=""):
    if user and user.is_active:
        updates.send([user], message, lead=lead, topic=topic, link=link)


def form_problems(form):
    """A form's errors as a sentence a person can read — no internal field names."""
    problems = []
    for field, errors in form.errors.items():
        label = form[field].label if field in form.fields else None
        for error in errors:
            problems.append(f"{label}: {error}" if label and field != "__all__" else error)
    return " ".join(problems)


@login_required
@require_POST
def scan_to_pdf(request, pk):
    """Merge photographed pages into one PDF and hand it straight back.

    Nothing is stored here. The browser attaches what comes back to the file
    box on the form the person is already filling in, so a scan travels the
    same path as a file they picked themselves and the stage is completed by
    the same submit button.
    """
    get_lead(request, pk)
    pages = request.FILES.getlist("pages")
    try:
        content = pages_to_pdf(pages)
    except ScanError as problem:
        return HttpResponseBadRequest(str(problem))

    filename = pdf_filename(request.POST.get("name"))
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = content_disposition_header(True, filename)
    # The browser reads the name off this rather than parsing the header. Percent-
    # encoded, because a header carries only plain ASCII and names may be in Tamil.
    response["X-Scan-Filename"] = quote(filename)
    return response


def search_leads(leads, query):
    """Narrow a list of leads to one customer: by name, number, place or reference."""
    query = (query or "").strip()
    if not query:
        return leads
    found = (
        Q(customer_name__icontains=query)
        | Q(phone__icontains=query)
        | Q(site_location__icontains=query)
        | Q(project_name__icontains=query)
        | Q(lead_number__icontains=query)
        | Q(quotation_number__icontains=query)
        | Q(invoice_number__icontains=query)
    )
    # Numbers are stored as ten bare digits, so "98765 43210" or "+91 98765…" is
    # searched the same way.
    digits = "".join(ch for ch in query if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) >= 4 and digits != query:
        found |= Q(phone__icontains=digits)
    return leads.filter(found)


def safe_next(request, fallback):
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(target)
    return redirect(fallback)


def stage_redirect(lead, stage_key):
    return redirect(f"{lead.get_absolute_url()}?stage={stage_key}")


def address(urlname, *args, **params):
    """A page's address with whichever of these query values are set."""
    url = reverse(urlname, args=args)
    params = {key: value for key, value in params.items() if value not in (None, "")}
    return f"{url}?{urlencode(params)}" if params else url


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


def save_uploads(lead, kind, uploaded_files, user):
    """Store every file chosen in one box — one or several — against the lead."""
    return [LeadFile.objects.create(lead=lead, kind=kind, file=uploaded, uploaded_by=user) for uploaded in uploaded_files]


def download(stored, filename=None):
    """A stored document handed over as a download.

    Never shown inside the app: on a phone the download opens in whatever PDF
    or image app the person uses, and the app stays exactly where it was.
    """
    try:
        handle = stored.open("rb")
    except (FileNotFoundError, OSError, ValueError):
        raise Http404("That file is no longer in storage.")
    return FileResponse(handle, as_attachment=True, filename=filename or stored.name.rsplit("/", 1)[-1])


@login_required
def lead_file(request, pk):
    """Any document on a lead, for whoever can open the lead."""
    upload = get_object_or_404(LeadFile.objects.select_related("lead"), pk=pk)
    get_lead(request, upload.lead_id)
    return download(upload.file)


@role_required(Role.ACCOUNTS)
def payment_receipt(request, pk):
    receipt = get_object_or_404(PaymentReceipt, pk=pk)
    return download(receipt.file)


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
            ("Awaiting Installation", "installation", "crm:installation_pending", "fa-helmet-safety", "tone-amber"),
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
    # "Updates for the day" — only what was routed to this person, and only what
    # still needs saying: finished work clears itself (see updates.py).
    todays_updates = (
        request.user.notifications.filter(created_at__date=today, dismissed=False).select_related("lead")[:25]
    )

    if request.user.role in (Role.SALESPERSON, Role.SUPER_ADMIN):
        return _sales_dashboard(request, todays_updates)

    counts = _pending_counts(ALL_QUEUE_KEYS, request.user)
    return render(
        request,
        "crm/dashboard_queue.html",
        {
            "updates": todays_updates,
            "cards": _queue_cards(request.user, counts),
            "my_todos": my_tasks(request.user).filter(done=False)[:8],
            **_handed_out(request.user),
            "accounts_totals": _accounts_totals() if request.user.role == Role.ACCOUNTS else None,
        },
    )


def my_tasks(user):
    """Someone's to-dos, with a quick enquiry still waiting on them at the top."""
    from .models import Enquiry

    waiting = Enquiry.objects.filter(task=OuterRef("pk"), outcome="")
    return (
        Task.objects.filter(assigned_to=user)
        .select_related("assigned_by")
        .annotate(from_enquiry=Exists(waiting))
        .order_by("-from_enquiry", "done", "due_date", "-created_at")
    )


def _handed_out(user):
    """The "Assigned by me" column that sits beside "My to-do" on every dashboard."""
    handed_out = Task.handed_out_by(user)
    return {
        "assigned_todos": handed_out[:8],
        "assigned_total": handed_out.count(),
        "assigned_completed": handed_out.filter(done=True).count(),
    }


def _sales_dashboard(request, todays_updates):
    leads = visible_leads(request.user)
    selected_salesperson = request.GET.get("salesperson") or ""
    if request.user.is_super_admin and selected_salesperson:
        leads = leads.filter(assigned_to_id=selected_salesperson)

    today = timezone.localdate()
    month_start = today.replace(day=1)
    # Only open leads have live follow-ups; a won or lost lead's are closed with it.
    followups = FollowUp.objects.filter(
        lead__in=leads, lead__status=Lead.Status.OPEN, done=False
    ).select_related("lead")

    # The Super Admin monitors rather than follows up, so instead of a reminder
    # list they see each sales executive's overdue work. The figures across the
    # top stay company-wide.
    overdue_by_person = None
    if request.user.is_super_admin:
        panel_followups = FollowUp.objects.none()
        overdue_by_person = _overdue_by_person()
        if selected_salesperson:
            overdue_by_person = [row for row in overdue_by_person if str(row["person"].pk) == selected_salesperson]
    else:
        # A reminder is for what needs doing now: everything overdue that nobody
        # has updated, and what is due today. Later ones wait on the Follow-up tab.
        panel_followups = followups.filter(date__lte=today)

    # Each card opens a list of exactly what it counts, for the same person.
    def lead_list(**params):
        return address("crm:lead_list", **params, salesperson=selected_salesperson)

    context = {
        "lead_bank": leads.count(),
        "leads_this_month": leads.filter(created_at__date__gte=month_start).count(),
        "overdue_followups": leads.filter(followups__in=followups.filter(FollowUp.overdue_q())).distinct().count(),
        "won_count": leads.filter(status=Lead.Status.WON).count(),
        "lost_count": leads.filter(status=Lead.Status.LOST).count(),
        "pending_quotations": leads.filter(status=Lead.Status.OPEN, quotation_uploaded_at__isnull=True).count(),
        "card_links": {
            "leads": lead_list(),
            "month": lead_list(period="month"),
            "overdue": lead_list(status="overdue"),
            "won": lead_list(status="won"),
            "lost": address("crm:lost_opportunities", salesperson=selected_salesperson),
            "waiting": lead_list(status="waiting"),
        },
        "open_followups": panel_followups,
        "today": today,
        "my_todos": my_tasks(request.user).filter(done=False)[:8],
        **_handed_out(request.user),
        "salespeople": sales_executives(),
        "selected_salesperson": selected_salesperson,
        "overdue_by_person": overdue_by_person,
        "updates": todays_updates,
        # Only the Super Admin can act on these, so only they are shown them.
        "password_requests": list(recovery.open_requests()) if request.user.is_super_admin else [],
    }
    return render(request, "crm/dashboard.html", context)


def _overdue_by_person():
    """How many leads each sales executive has an overdue follow-up on.

    Someone since removed still appears while their leads carry overdue calls,
    so the work does not vanish from sight before it is reassigned.
    """
    overdue = FollowUp.objects.filter(FollowUp.overdue_q(), lead__status=Lead.Status.OPEN)
    counts = {
        row["lead__assigned_to"]: row["n"]
        for row in overdue.values("lead__assigned_to").annotate(n=Count("lead", distinct=True))
    }
    people = list(sales_executives())
    listed = {person.pk for person in people}
    people += [person for person in User.objects.filter(pk__in=counts, is_active=False) if person.pk not in listed]
    rows = [{"person": person, "overdue": counts.get(person.pk, 0)} for person in people]
    return sorted(rows, key=lambda row: -row["overdue"])


# ---------------------------------------------------------------------------
# leads
# ---------------------------------------------------------------------------


@role_required(Role.SALESPERSON)
def lead_list(request):
    leads = visible_leads(request.user)
    query = request.GET.get("q", "").strip()
    selected_salesperson = request.GET.get("salesperson") or ""
    leads = search_leads(leads, query)
    if request.user.is_super_admin and selected_salesperson:
        leads = leads.filter(assigned_to_id=selected_salesperson)

    status = request.GET.get("status") or ""
    status_choices = dict(LEAD_FILTERS)
    if status not in status_choices:
        status = ""
    leads = filter_leads(leads, status)

    # "This month" narrows to what the dashboard and pipeline count for the month:
    # leads added this month, or for won and lost, decided this month.
    period = request.GET.get("period") or ""
    if period == "month":
        month_start = timezone.localdate().replace(day=1)
        stamp = {"won": "won_at", "lost": "lost_at"}.get(status, "created_at")
        leads = leads.filter(**{f"{stamp}__date__gte": month_start})
    else:
        period = ""

    # "Waiting over 3 days", as the pipeline's attention list counts it.
    older = request.GET.get("older") or ""
    if older.isdigit():
        leads = leads.filter(created_at__lte=timezone.now() - timedelta(days=int(older)))
    else:
        older = ""

    heading = status_choices.get(status, "")
    if period:
        heading = f"{heading or 'Added'} this month"
    if older:
        heading = f"{heading or 'Leads'}, over {older} days"

    return render(
        request,
        "crm/lead_list.html",
        {
            "leads": leads,
            "q": query,
            "salespeople": sales_executives(),
            "selected_salesperson": selected_salesperson,
            "status": status,
            "period": period,
            "older": older,
            "filter_heading": heading,
            "status_choices": LEAD_FILTERS,
        },
    )


LEAD_FILTERS = [
    ("waiting", "Waiting for a quotation"),
    ("unchased", "Quoted, no call booked"),
    ("following", "In follow-up"),
    ("followup", "Follow-up stage"),
    ("won", "Won"),
    ("lost", "Lost"),
    ("overdue", "Overdue follow-up"),
]


def filter_leads(leads, status):
    """The Leads list's filters. The pipeline and dashboard count with the same rules."""
    if status in ("waiting", "unchased", "following"):
        # The pipeline's stages, so each line there opens to exactly its leads.
        open_leads = leads.filter(status=Lead.Status.OPEN)
        quoted = open_leads.filter(quotation_uploaded_at__isnull=False)
        chased = FollowUp.objects.filter(done=False, lead__in=quoted).values("lead_id")
        return {
            "waiting": open_leads.filter(quotation_uploaded_at__isnull=True),
            "unchased": quoted.exclude(pk__in=chased),
            "following": quoted.filter(pk__in=chased),
        }[status]
    if status == "won":
        return leads.filter(status=Lead.Status.WON)
    if status == "lost":
        return leads.filter(status=Lead.Status.LOST)
    if status == "followup":
        return leads.filter(status=Lead.Status.OPEN, quotation_uploaded_at__isnull=False)
    if status == "overdue":
        overdue = FollowUp.objects.filter(FollowUp.overdue_q()).values("lead_id")
        return leads.filter(status=Lead.Status.OPEN, pk__in=overdue)
    return leads


@role_required(Role.SALESPERSON)
def lead_create(request):
    from . import enquiries

    # Made from a quick enquiry: the form starts with what the Super Admin passed on.
    enquiry = enquiries.for_new_lead(request)
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
            if enquiry is not None:
                enquiries.settle(enquiry, request.user, enquiry.Outcome.LEAD, lead=lead)
            messages.success(request, f"Lead for {lead.customer_name} saved. Set the first follow-up below.")
            return redirect(lead.get_absolute_url())
    else:
        initial = {}
        if enquiry is not None:
            initial = {"customer_name": enquiry.customer_name, "phone": enquiry.phone,
                       "remarks": f"Phone enquiry passed on by {enquiry.created_by.display_name if enquiry.created_by else 'the Super Admin'}" + (f": {enquiry.remarks}" if enquiry.remarks else ".")}
        form = LeadForm(user=request.user, initial=initial)
    return render(request, "crm/lead_form.html", {"form": form, "enquiry": enquiry})


@role_required(Role.SALESPERSON)
def lead_edit(request, pk):
    lead = get_lead(request, pk)
    was_assigned_to = lead.assigned_to_id
    if request.method == "POST":
        form = LeadForm(request.POST, instance=lead, user=request.user)
        if form.is_valid():
            lead = form.save()
            if lead.assigned_to_id != was_assigned_to:
                # Work already done keeps the name of whoever did it; this row
                # is what lets the timeline say when the hand-over happened.
                LeadAssignment.objects.create(
                    lead=lead,
                    from_user_id=was_assigned_to,
                    to_user=lead.assigned_to,
                    changed_by=request.user,
                )
                # The previous owner can no longer open the lead, so nothing about
                # it should be left waiting on their dashboard.
                previous = User.objects.filter(pk=was_assigned_to).first()
                if previous and previous.role == Role.SALESPERSON:
                    updates.clear_for(previous, lead)
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


@role_required(Role.SUPER_ADMIN)
@require_POST
def lead_delete(request, pk):
    """Only the Super Admin deletes a lead — even a confirmed order, with everything on it.

    A sales executive marks a lead lost instead. A won lead takes its payments, the
    installer's ledger and its paperwork with it, so the page asks twice.
    """
    lead = get_lead(request, pk)
    name = lead.customer_name
    stored = lead.stored_files()
    lead.delete()
    # The rows went with the lead; the files themselves have to be removed too, or
    # they sit in the bucket taking up room nobody can see.
    failed = 0
    for file in stored:
        try:
            file.delete(save=False)
        except Exception:
            failed += 1
    # The dashboard's storage bar is remembered for an hour; measure again now.
    storage_usage.refresh()
    messages.success(request, f"Lead for {name} deleted, with {len(stored) - failed} stored file(s).")
    if failed:
        messages.warning(request, f"{failed} file(s) could not be removed from storage and may still be taking up room.")
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
        # Won or lost can be called on an open lead once a quotation is out — even
        # while a revision is pending, which keeps step 4 open to be read.
        "decision_open": lead.status == Lead.Status.OPEN and lead.quotation_uploaded_at is not None,
        "sheet_awaiting_approval": bool(
            lead.production_sheet_at and not lead.production_approved_at and not lead.production_revision_at
        ),
        "measurement_form": MeasurementBoxForm(),
        "rough_form": RoughMeasurementForm(),
        "quotation_form": QuotationForm(),
        "caf_form": CafFinalForm(),
        "production_form": FilesForm(),
        "checklist_form": ChecklistForm(instance=lead),
        "dispatch_form": DispatchForm(instance=lead),
        "warranty_form": FilesForm(),
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
    # A new lead is chased from day one: its first follow-up is booked before it
    # moves on to measurements.
    if not lead.followups.exists():
        messages.error(request, "Book the first follow-up for this lead before moving on to measurements.")
        return stage_redirect(lead, stage_flow.LEAD)

    form = MeasurementBoxForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, form_problems(form))
        return stage_redirect(lead, stage_flow.LEAD)

    mode = form.cleaned_data["mode"]
    lead.measurement_mode = mode
    now = timezone.now()

    if mode == Lead.MeasurementMode.REQUESTED:
        lead.measurement_requested_at = now
        lead.measurement_requested_by = request.user
        # Whatever map link came with the request stays on the lead, so the final
        # measurement visit later has it too.
        if form.cleaned_data.get("site_map_link"):
            lead.site_map_link = form.cleaned_data["site_map_link"]
        allocated = form.cleaned_data.get("assign_to")
        lead.measurement_assigned_to = allocated
        lead.save()
        message = (
            f"Rough measurement needed — {lead.customer_name}, {lead.site_location} "
            f"(site stage: {lead.get_site_stage_display()})"
        )
        if allocated:
            # Told to one person, so only that person is chased for it.
            notify_user(lead, message, allocated, topic=updates.ROUGH)
            messages.success(request, f"Rough measurement allocated to {allocated.display_name}.")
        else:
            notify(lead, message, Role.MEASUREMENT, topic=updates.ROUGH)
            messages.success(request, "Rough measurement request sent to the measurement team.")
    else:
        save_uploads(lead, LeadFile.Kind.ROUGH_MEASUREMENT, form.cleaned_data["file"], request.user)
        lead.measurement_notes = form.cleaned_data.get("notes", "")
        # Measurements already in hand, so the rough measurement stage is complete.
        lead.measurement_done_at = now
        lead.measurement_done_by = request.user
        lead.save()
        notify(lead, f"Measurements ready for quotation — {lead.customer_name}", Role.QUOTATION, topic=updates.QUOTATION)
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
        messages.error(request, form_problems(form))
        return stage_redirect(lead, stage_flow.ROUGH)

    save_uploads(lead, LeadFile.Kind.ROUGH_MEASUREMENT, form.cleaned_data["file"], request.user)
    if form.cleaned_data.get("notes"):
        lead.measurement_notes = form.cleaned_data["notes"]
    lead.measurement_done_at = timezone.now()
    lead.measurement_done_by = request.user
    lead.save()
    updates.clear(updates.ROUGH, lead=lead)
    notify(lead, f"Measurements ready for quotation — {lead.customer_name}", Role.QUOTATION, topic=updates.QUOTATION)
    # News for the sales executive until the quotation it leads to arrives.
    notify_user(lead, f"Rough measurement completed for {lead.customer_name}", lead.assigned_to, topic=updates.QUOTATION)
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

    # A revision keeps the elevation report already on file unless a new one comes with it.
    form = QuotationForm(request.POST, request.FILES, has_elevation=lead.elevation_files.exists())
    if not form.is_valid():
        messages.error(request, form_problems(form))
        return stage_redirect(lead, stage_flow.QUOTATION)

    # What this upload replaces stays on file, marked as replaced, so the price the
    # sales executive sends is always the latest one. Marked only once the new files
    # are safely stored, so a failed upload never leaves a lead with no quotation.
    now = timezone.now()
    added = save_uploads(lead, LeadFile.Kind.QUOTATION, form.cleaned_data["files"], request.user)
    lead.uploads.filter(kind=LeadFile.Kind.QUOTATION, replaced_at__isnull=True).exclude(
        pk__in=[upload.pk for upload in added]
    ).update(replaced_at=now)
    if form.cleaned_data.get("elevation"):
        elevations = save_uploads(lead, LeadFile.Kind.ELEVATION, form.cleaned_data["elevation"], request.user)
        lead.uploads.filter(kind=LeadFile.Kind.ELEVATION, replaced_at__isnull=True).exclude(
            pk__in=[upload.pk for upload in elevations]
        ).update(replaced_at=now)
    lead.quotation_number = form.cleaned_data["quotation_number"]
    lead.quotation_uploaded_at = timezone.now()
    lead.quotation_uploaded_by = request.user
    revised = lead.quotation_revision_pending
    lead.quotation_revision_pending = False
    lead.save()
    updates.clear(updates.QUOTATION, lead=lead)
    if revised:
        notify_user(lead, f"Revised quotation {lead.quotation_number} uploaded for {lead.customer_name}",
                    lead.assigned_to, topic=updates.DECISION)
        messages.success(request, "Revised quotation uploaded and sent back to the sales executive.")
    else:
        notify_user(lead, f"Quotation {lead.quotation_number} uploaded for {lead.customer_name}",
                    lead.assigned_to, topic=updates.DECISION)
        messages.success(request, "Quotation uploaded and forwarded to the sales executive.")
    return redirect(lead.get_absolute_url())


# ---------------------------------------------------------------------------
# stage 4 — won / lost
# ---------------------------------------------------------------------------


def guard_decision(request, lead, needs_quotation):
    """Won or lost is the sales executive's call on an open lead.

    Lost can be called at any point: customers drop out before a price is sent
    too. Won needs a quotation to have gone out — and is allowed while a revision
    is pending, for when the customer takes the price as it stands after all.
    """
    if not stage_flow.can_act(request.user, stage_flow.DECISION):
        return HttpResponseForbidden("Your role cannot act on this stage.")
    if lead.status != Lead.Status.OPEN:
        messages.error(request, "This lead is already closed.")
        return redirect(lead.get_absolute_url())
    if needs_quotation and not lead.quotation_uploaded_at:
        messages.error(request, "An order can only be confirmed once a quotation has gone out.")
        return redirect(lead.get_absolute_url())
    return None


def close_followups(lead):
    """A won or lost lead has nothing left to chase; its open follow-up closes with it."""
    FollowUp.objects.filter(lead=lead, done=False).update(done=True, done_at=timezone.now(), closed_with_lead=True)


@role_required(Role.SALESPERSON)
def stage_won(request, pk):
    lead = get_lead(request, pk)
    blocked = guard_decision(request, lead, needs_quotation=True)
    if blocked:
        return blocked

    if request.method == "POST":
        form = WonForm(request.POST, instance=lead)
        if form.is_valid():
            lead = form.save(commit=False)
            lead.status = Lead.Status.WON
            lead.won_at = timezone.now()
            lead.won_by = request.user
            # Taken at the price already quoted, so no revision is coming.
            lead.quotation_revision_pending = False
            lead.save()
            close_followups(lead)
            updates.clear(updates.ROUGH, updates.QUOTATION, updates.DECISION, lead=lead)
            notify(
                lead,
                f"Order confirmed — {lead.customer_name}: value {rupees(lead.order_value)}, "
                f"advance {rupees(lead.advance_received)}, balance {rupees(lead.balance_amount)}",
                Role.ACCOUNTS,
            )
            notify(lead, f"CAF & final measurement pending — {lead.customer_name}", Role.MEASUREMENT, topic=updates.CAF)
            messages.success(request, "Order confirmed. Accounts and the measurement team have been notified.")
            return redirect(lead.get_absolute_url())
    else:
        form = WonForm(instance=lead)
    return render(request, "crm/won_form.html", {"lead": lead, "form": form})


@role_required(Role.SALESPERSON)
def stage_lost(request, pk):
    lead = get_lead(request, pk)
    blocked = guard_decision(request, lead, needs_quotation=False)
    if blocked:
        return blocked

    if request.method == "POST":
        form = LostForm(request.POST, instance=lead)
        if form.is_valid():
            lead = form.save(commit=False)
            lead.status = Lead.Status.LOST
            lead.lost_at = timezone.now()
            lead.lost_by = request.user
            lead.quotation_revision_pending = False
            lead.save()
            close_followups(lead)
            # Whatever anyone was asked to do for this lead, it is no longer needed.
            updates.clear(*updates.LEAD_WORK, lead=lead)
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
        messages.error(request, form_problems(form))
        return stage_redirect(lead, stage_flow.CAF)

    now = timezone.now()
    if form.cleaned_data.get("caf_signed"):
        save_uploads(lead, LeadFile.Kind.CAF_SIGNED, form.cleaned_data["caf_signed"], request.user)
        lead.caf_signed_at = now
    if form.cleaned_data.get("final_measurement"):
        save_uploads(lead, LeadFile.Kind.FINAL_MEASUREMENT, form.cleaned_data["final_measurement"], request.user)
        lead.final_measurement_at = now
    lead.caf_final_by = request.user
    lead.save()

    if lead.caf_signed_at and lead.final_measurement_at:
        updates.clear(updates.CAF, lead=lead)
        notify(lead, f"Final measurement ready — production sheet needed for {lead.customer_name}",
               Role.PRODUCTION, topic=updates.SHEET)
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

    form = FilesForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, form_problems(form) or "Choose the production sheet file to upload.")
        return stage_redirect(lead, stage_flow.PRODUCTION)

    # The superseded sheet goes, so nobody works from the wrong drawing — once the
    # new one is safely stored.
    sheets = save_uploads(lead, LeadFile.Kind.PRODUCTION_SHEET, form.cleaned_data["file"], request.user)
    for stale in lead.production_sheet_files.exclude(pk__in=[sheet.pk for sheet in sheets]):
        stale.file.delete(save=False)
        stale.delete()
    lead.production_sheet_at = timezone.now()
    lead.production_sheet_by = request.user
    lead.production_approved_at = None
    lead.production_approved_by = None
    lead.production_revision_note = ""
    lead.production_revision_at = None
    lead.save()
    # The sheet asked for is in; any earlier approval request was for the old one.
    updates.clear(updates.SHEET, updates.APPROVAL, lead=lead)
    notify(lead, f"Production sheet awaiting your approval — {lead.customer_name}", Role.MEASUREMENT, topic=updates.APPROVAL)
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
    updates.clear(updates.APPROVAL, updates.SHEET, lead=lead)
    notify(lead, f"Production sheet approved — {lead.customer_name}", Role.PRODUCTION, topic=updates.FLOOR)
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
    updates.clear(updates.APPROVAL, lead=lead)
    notify(lead, f"Production sheet needs revision — {lead.customer_name}: {remarks}", Role.PRODUCTION, topic=updates.SHEET)
    messages.success(request, "Sent back to the production team with your remarks.")
    return redirect(lead.get_absolute_url())


@role_required(Role.SALESPERSON)
@require_POST
def quotation_need_revision(request, pk):
    """The same loop the production sheet has, one stage earlier."""
    lead = get_lead(request, pk)
    if not lead.quotation_uploaded_at:
        messages.error(request, "There is no quotation to send back yet.")
        return redirect(lead.get_absolute_url())
    if lead.status != Lead.Status.OPEN:
        messages.error(request, "This lead is already closed.")
        return redirect(lead.get_absolute_url())

    remarks = request.POST.get("remarks", "").strip()
    if not remarks:
        messages.error(request, "Say what needs changing before sending the quotation back.")
        return stage_redirect(lead, stage_flow.DECISION)

    lead.quotation_revision_pending = True
    lead.save(update_fields=["quotation_revision_pending"])
    QuotationRevision.objects.create(lead=lead, note=remarks, requested_by=request.user)
    # The sales executive has answered the quotation they were sent.
    updates.clear(updates.DECISION, lead=lead)
    notify(lead, f"Quotation needs revision — {lead.customer_name}: {remarks}", Role.QUOTATION, topic=updates.QUOTATION)
    messages.success(request, "Sent back to the quotation team with your remarks.")
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


# Where a wrongly-moved job goes back to.
FABRICATION_BACK = {
    Lead.Fabrication.UNDER: (Lead.Fabrication.FUTURE, "Future Production"),
    Lead.Fabrication.READY: (Lead.Fabrication.UNDER, "Under Production"),
}


@role_required(Role.PRODUCTION)
@require_POST
def fabrication_back(request, pk):
    """Undo a move between columns. Only before the order has been dispatched."""
    lead = get_lead(request, pk)
    blocked = guard_stage(request, lead, stage_flow.FABRICATION)
    if blocked:
        return blocked

    step_back = FABRICATION_BACK.get(lead.fabrication_column)
    if not step_back or lead.dispatched_at:
        messages.error(request, "This order cannot be moved back.")
        return safe_next(request, lead.get_absolute_url())

    column, label = step_back
    lead.fabrication_column = column
    lead.save(update_fields=["fabrication_column"])
    messages.success(request, f"{lead.customer_name} moved back to {label}.")
    return safe_next(request, lead.get_absolute_url())


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
            # The installer is paid by the sq ft: the rate times the site's area.
            if lead.installation_rate and lead.total_sqft:
                lead.installation_charge = installation_total(lead.installation_rate, lead.total_sqft)
            lead.save()
            updates.clear(updates.FLOOR, lead=lead)
            others = [person for person in queues.installation_people() if person.pk != request.user.pk]
            updates.send(others, f"Dispatched — installation pending for {lead.customer_name}, {lead.site_location}",
                         lead=lead, topic=updates.INSTALL)
            messages.success(
                request,
                "Dispatched. It waits under Installation until the site is marked installed; handover opens after that.",
            )
            return safe_next(request, lead.get_absolute_url())
    else:
        form = DispatchForm(instance=lead)
    # Only an address on this site goes back into the page's links.
    back = request.GET.get("next") or request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}):
        back = ""
    return render(request, "crm/dispatch_form.html", {"lead": lead, "form": form, "next": back})


# ---------------------------------------------------------------------------
# stage 8 — warranty & handover (field manager)
# ---------------------------------------------------------------------------


# Both certificates are a job's own paperwork rather than a stage action, and
# the completed-projects list offers them to the sales executive too. get_lead
# still keeps a sales executive to their own leads.
@login_required
def warranty_download(request, pk):
    """The guarantee certificate the customer keeps."""
    lead = get_lead(request, pk)
    if not lead.dispatched_at:
        raise Http404
    return render_warranty_certificate(lead)


@login_required
def handover_download(request, pk):
    """The certificate the customer signs, filled in from the job."""
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

    form = FilesForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, form_problems(form) or "Choose the signed handover certificate to upload.")
        return stage_redirect(lead, stage_flow.WARRANTY)

    save_uploads(lead, LeadFile.Kind.HANDOVER_SIGNED, form.cleaned_data["file"], request.user)
    lead.handover_signed_at = timezone.now()
    lead.handover_signed_by = request.user
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
    updates.clear(updates.HANDOVER, lead=lead)
    notify_user(lead, f"Project completed — {lead.customer_name}", lead.assigned_to,
                link=updates.completed_link(lead))
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
        # A won or lost lead's follow-up closes with it and cannot be worked any more.
        items = items.filter(done=False, lead__status=Lead.Status.OPEN)
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
        messages.error(request, form_problems(form))
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


def _days_since(when):
    return (timezone.now() - when).days if when else None


@role_required(Role.SALESPERSON)
def pipeline(request):
    """Where the open leads stand, as a funnel — a line a stage, the leads behind it on demand."""
    leads = visible_leads(request.user)
    selected_salesperson = request.GET.get("salesperson") or ""
    if request.user.is_super_admin and selected_salesperson:
        leads = leads.filter(assigned_to_id=selected_salesperson)

    today = timezone.localdate()
    month_start = today.replace(day=1)
    open_leads = leads.filter(status=Lead.Status.OPEN)
    quoted = open_leads.filter(quotation_uploaded_at__isnull=False)
    chased = FollowUp.objects.filter(done=False, lead__in=quoted).values("lead_id")

    waiting = open_leads.filter(quotation_uploaded_at__isnull=True)
    following = quoted.filter(pk__in=chased)
    unchased = quoted.exclude(pk__in=chased)
    won = leads.filter(status=Lead.Status.WON, won_at__date__gte=month_start)
    lost = leads.filter(status=Lead.Status.LOST, lost_at__date__gte=month_start)

    def stage(key, title, hint, queryset, value_field, tone, meta, link):
        totals = queryset.aggregate(n=Count("pk"), v=Sum(value_field))
        top = queryset.select_related("assigned_to").order_by(F(value_field).desc(nulls_last=True), "-updated_at")[:6]
        return {
            "key": key,
            "title": title,
            "hint": hint,
            "count": totals["n"] or 0,
            "value": totals["v"] or Decimal("0"),
            "tone": tone,
            "link": link,
            "top": [
                {"lead": lead, "value": getattr(lead, value_field), "meta": meta(lead)}
                for lead in top
            ],
        }

    def ago(days):
        return "today" if days == 0 else f"{days} day{'s' if days != 1 else ''} ago"

    def waited(lead):
        return f"added {ago(_days_since(lead.created_at))}"

    def quoted_ago(lead):
        return f"quoted {ago(_days_since(lead.quotation_uploaded_at))}"

    def next_call(lead):
        due = lead.open_followup
        return f"call {due.date:%d %b}" if due else "no call booked"

    def local_day(when):
        return f"{timezone.localtime(when):%d %b}"

    def lead_list(**params):
        # The list each line opens counts with the same rules as the line.
        return address("crm:lead_list", **params, salesperson=selected_salesperson)

    stages = [
        stage("waiting", "Waiting for a quotation", "Measured or requested, no price sent yet",
              waiting, "expected_value", "gold", waited, lead_list(status="waiting")),
        stage("unchased", "Quoted, no call booked", "A price is out and nothing is scheduled",
              unchased, "expected_value", "amber", quoted_ago, lead_list(status="unchased")),
        stage("following", "In follow-up", "A price is out and a call is booked",
              following, "expected_value", "blue", next_call, lead_list(status="following")),
        stage("won", "Won this month", "Orders confirmed since the 1st",
              won, "order_value", "green", lambda l: f"won {local_day(l.won_at)}", lead_list(status="won", period="month")),
        stage("lost", "Lost this month", "Did not come off since the 1st",
              lost, "expected_value", "rose", lambda l: f"lost {local_day(l.lost_at)}", lead_list(status="lost", period="month")),
    ]
    biggest = max((row["count"] for row in stages), default=0) or 1
    for row in stages:
        row["bar"] = max(4, round(row["count"] * 100 / biggest)) if row["count"] else 0

    open_value = open_leads.aggregate(v=Sum("expected_value"))["v"] or Decimal("0")
    decided = stages[3]["count"] + stages[4]["count"]
    win_rate = round(stages[3]["count"] * 100 / decided) if decided else None

    overdue_leads = (
        FollowUp.objects.filter(FollowUp.overdue_q(), lead__in=open_leads).values("lead_id").distinct().count()
    )
    slow = waiting.filter(created_at__lte=timezone.now() - timedelta(days=3)).count()
    attention = []
    if overdue_leads:
        attention.append({"count": overdue_leads, "text": "with a follow-up that is overdue", "link": lead_list(status="overdue")})
    if stages[1]["count"]:
        attention.append({"count": stages[1]["count"], "text": "quoted but no call booked", "link": lead_list(status="unchased")})
    if slow:
        attention.append({"count": slow, "text": "waiting on a quotation for over 3 days", "link": lead_list(status="waiting", older=3)})

    by_executive = None
    if request.user.is_super_admin and not selected_salesperson:
        by_executive = []
        for person in sales_executives():
            mine = open_leads.filter(assigned_to=person)
            by_executive.append(
                {
                    "person": person,
                    "open": mine.count(),
                    "value": mine.aggregate(v=Sum("expected_value"))["v"] or Decimal("0"),
                    "overdue": FollowUp.objects.filter(FollowUp.overdue_q(), lead__in=mine).values("lead_id").distinct().count(),
                    "won": won.filter(assigned_to=person).aggregate(v=Sum("order_value"))["v"] or Decimal("0"),
                }
            )
        # Someone with nothing open and nothing won is only a line of zeros.
        by_executive = [row for row in by_executive if row["open"] or row["won"]]
        by_executive.sort(key=lambda row: -row["value"])

    return render(
        request,
        "crm/pipeline.html",
        {
            "stages": stages,
            "open_count": open_leads.count(),
            "open_value": open_value,
            "won_value": stages[3]["value"],
            "win_rate": win_rate,
            "attention": attention,
            "by_executive": by_executive,
            "month": month_start,
            "salespeople": sales_executives(),
            "selected_salesperson": selected_salesperson,
        },
    )


class TeamTarget:
    """Everyone's targets for the month added together, for the Super Admin's overview."""

    salesperson = "the whole team"

    def __init__(self, targets, won):
        self.targets = targets
        self.amount = sum((target.amount for target in targets), Decimal("0"))
        self.achieved = won.aggregate(total=Sum("order_value"))["total"] or Decimal("0")

    def __bool__(self):
        return bool(self.targets)

    @property
    def pending(self):
        return max(self.amount - self.achieved, Decimal("0"))

    @property
    def percent(self):
        return min(int(self.achieved / self.amount * 100), 100) if self.amount else 0


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
    in_month = {"won_at__year": this_month.year, "won_at__month": this_month.month}
    lost_in_month = {"lost_at__year": this_month.year, "lost_at__month": this_month.month}
    won_this_month = []
    lost_this_month = []
    if request.user.is_super_admin and not selected_salesperson:
        # Everyone's at once: the team's combined target against everything won,
        # the way the Summary for the Month reckons it.
        won_this_month = Lead.objects.filter(status=Lead.Status.WON, **in_month).order_by("-won_at")
        current = TeamTarget(list(target_qs.filter(month=this_month)), won_this_month)
        if current:
            lost_this_month = Lead.objects.filter(status=Lead.Status.LOST, **lost_in_month).order_by("-lost_at")
        else:
            won_this_month = []
    else:
        current = target_qs.filter(month=this_month).first()
    if current and not isinstance(current, TeamTarget):
        # The same orders the Achieved figure adds up (see models.credited_q).
        won_this_month = current.won_leads.order_by("-won_at")
        # A loss is theirs by the same rule: whoever marked it, unless the Super Admin did.
        person = current.salesperson
        theirs = Q(lost_by=person, lost_by__role=Role.SALESPERSON) | (
            Q(assigned_to=person) & (Q(lost_by__isnull=True) | ~Q(lost_by__role=Role.SALESPERSON))
        )
        lost_this_month = Lead.objects.filter(theirs, status=Lead.Status.LOST, **lost_in_month).order_by("-lost_at")
    return render(
        request,
        "crm/targets.html",
        {
            "form": form,
            "targets": target_qs,
            "current": current,
            "this_month": this_month,
            "won_this_month": won_this_month,
            "lost_this_month": lost_this_month,
            "salespeople": sales_executives(),
            "selected_salesperson": selected_salesperson,
        },
    )


@role_required(Role.SALESPERSON)
def lost_opportunities(request):
    leads = visible_leads(request.user).filter(status=Lead.Status.LOST)
    query = request.GET.get("q", "").strip()
    leads = search_leads(leads, query)
    selected_salesperson = request.GET.get("salesperson") or ""
    if request.user.is_super_admin and selected_salesperson:
        leads = leads.filter(assigned_to_id=selected_salesperson)
    return render(
        request,
        "crm/lost_list.html",
        {
            "q": query,
            "leads": leads,
            "salespeople": sales_executives(),
            "selected_salesperson": selected_salesperson,
        },
    )


@role_required(Role.SALESPERSON)
def completed_projects(request):
    leads = visible_leads(request.user).filter(completed_at__isnull=False).prefetch_related(
        "payments", "invoice_charges", "complaints"
    )
    query = request.GET.get("q", "").strip()
    return render(request, "crm/completed_list.html", {"leads": search_leads(leads, query), "q": query})


# ---------------------------------------------------------------------------
# role queues
# ---------------------------------------------------------------------------


def _queue(request, template, leads, title, blurb):
    return render(request, template, {"leads": leads, "title": title, "blurb": blurb})


@role_required(Role.MEASUREMENT)
def queue_rough(request):
    # Everyone on the team sees every request, so one can cover for another; the
    # ones allocated to you (or to nobody) come first, and are what your badge counts.
    mine = queues.rough_for(request.user).values("pk")
    leads = (
        queues.rough()
        .select_related("assigned_to", "measurement_assigned_to")
        .annotate(for_me=Count("pk", filter=Q(pk__in=mine)))
        .order_by("-for_me", "measurement_requested_at")
    )
    return render(
        request,
        "crm/queues/simple.html",
        {
            "leads": leads,
            "title": "Rough Measurements",
            "blurb": "Leads waiting for a rough measurement. Yours, and ones left for anyone, are at the top.",
            "show_allocation": True,
        },
    )


@role_required(Role.MEASUREMENT)
def queue_final(request):
    leads = queues.final().select_related("assigned_to")
    return _queue(
        request,
        "crm/queues/simple.html",
        leads,
        "Final Measurements",
        "Confirmed orders waiting for the signed CAF and the final measurement.",
    )


@role_required(Role.MEASUREMENT)
def queue_production_validation(request):
    # A sheet sent back is with the production team until they upload it again.
    leads = queues.validation().select_related("assigned_to")
    return _queue(
        request,
        "crm/queues/simple.html",
        leads,
        "Production Sheet Validation",
        "Production sheets waiting for your approval.",
    )


@role_required(Role.QUOTATION)
def queue_quotations(request):
    # Waiting on a first quotation, or on a revision the sales executive asked for.
    leads = queues.quotation().select_related("assigned_to")
    return _queue(
        request,
        "crm/queues/simple.html",
        leads,
        "Quotation Upload",
        "Customers whose measurements are in and are waiting for a quotation, "
        "plus any quotation sent back for revision.",
    )


def _accounts_totals(leads=None):
    # "Order value" is what the customer is billed, so anything accounts added
    # to an invoice has to count towards it here too.
    if leads is None:
        leads = Lead.objects.filter(status=Lead.Status.WON)
    leads = leads.prefetch_related("payments", "invoice_charges")
    totals = leads.aggregate(advance=Sum("advance_received"))
    totals["value"] = sum((lead.invoice_total or Decimal("0")) for lead in leads)
    totals["extras"] = sum(lead.extra_charges for lead in leads)
    totals["outstanding"] = sum(
        (lead.balance_amount or Decimal("0")) for lead in leads if lead.is_outstanding
    )
    return totals


def _orders():
    return (
        Lead.objects.filter(status=Lead.Status.WON)
        .select_related("assigned_to", "won_by")
        .prefetch_related("payments", "invoice_charges")
    )


def order_sellers():
    """Everyone with a confirmed order to their name, for the accounts filter.

    An order belongs to the sales executive it counts towards (credited_q) — the
    same person the targets and the monthly summary give it to.
    """
    orders = Lead.objects.filter(status=Lead.Status.WON).select_related("assigned_to", "won_by")
    people = {lead.credited_to for lead in orders if lead.credited_to is not None}
    return sorted(people, key=lambda person: person.display_name.lower())


def _seller(request, sellers):
    """The sales executive picked in the filter, if it is one of them."""
    picked = request.GET.get("salesperson", "")
    return next((person for person in sellers if str(person.pk) == picked), None)


@role_required(Role.ACCOUNTS)
def queue_accounts(request):
    leads = _orders()
    sellers = order_sellers()
    seller = _seller(request, sellers)
    if seller is not None:
        leads = leads.filter(credited_q(seller))
    # The figures follow the sales executive picked; a search does not narrow them.
    totals = _accounts_totals(leads if seller is not None else None)
    query = request.GET.get("q", "").strip()
    leads = search_leads(leads, query)
    range_key = aging.clean_key(request.GET.get("range"))
    # One sales executive's list is for chasing their customers' dues, so it
    # shows only what is still owed unless the paid-up orders are asked for too.
    paid_too = seller is not None and request.GET.get("paid") == "1"
    outstanding_only = range_key != "all" or (seller is not None and not paid_too)
    shown = aging.only_in_range(leads, range_key) if outstanding_only else leads

    def statement(**params):
        return address("crm:outstanding_pdf", salesperson=seller.pk if seller else "", **params)

    return render(
        request,
        "crm/queues/accounts.html",
        {
            "leads": shown,
            "shown_due": sum(((lead.balance_amount or Decimal("0")) for lead in shown if lead.is_outstanding), Decimal("0")),
            "totals": totals,
            "q": query,
            "range_key": range_key,
            "range_label": aging.label(range_key),
            "ranges": [(key, label) for key, label, *_ in aging.RANGES],
            "sellers": sellers,
            "seller": seller,
            "paid_too": paid_too,
            "statement_url": statement(range=range_key if range_key != "all" else ""),
            "company_statements": [
                (key, label, address("crm:outstanding_pdf", range=key if key != "all" else ""))
                for key, label, *_ in aging.RANGES
            ],
            "toggle_paid_url": address(
                "crm:queue_accounts", q=query, range=range_key if range_key != "all" else "",
                salesperson=seller.pk if seller else "", paid="" if paid_too else "1",
            ),
        },
    )


@role_required(Role.ACCOUNTS)
def ledger(request, pk):
    """A confirmed order's payment ledger — post entries and correct the figures."""
    lead = get_object_or_404(
        Lead.objects.prefetch_related("payments__receipts", "invoice_charges"), pk=pk, status=Lead.Status.WON
    )
    payment_form = PaymentForm(lead=lead)
    ledger_form = LedgerForm(instance=lead)
    charge_form = InvoiceChargeForm()

    if request.method == "POST":
        if "save_figures" in request.POST:
            # Its own copy of the order: a form that fails would otherwise leave its
            # unsaved figures on the lead, and the page would show them as if saved.
            ledger_form = LedgerForm(request.POST, instance=Lead.objects.get(pk=lead.pk))
            if ledger_form.is_valid():
                ledger_form.save()
                messages.success(request, "Order figures updated.")
                return redirect("crm:ledger", pk=lead.pk)
        elif "add_charge" in request.POST:
            charge_form = InvoiceChargeForm(request.POST)
            if charge_form.is_valid():
                charge = charge_form.save(commit=False)
                charge.lead = lead
                charge.added_by = request.user
                charge.save()
                messages.success(request, f"{charge.description} added to the invoice.")
                return redirect("crm:ledger", pk=lead.pk)
        else:
            payment_form = PaymentForm(request.POST, request.FILES, lead=lead)
            if payment_form.is_valid():
                payment = payment_form.save(commit=False)
                payment.lead = lead
                payment.recorded_by = request.user
                payment.save()
                for upload in payment_form.cleaned_data["files"]:
                    PaymentReceipt.objects.create(payment=payment, file=upload)
                messages.success(request, "Payment entry posted.")
                return redirect("crm:ledger", pk=lead.pk)

    return render(
        request,
        "crm/queues/ledger.html",
        {
            "lead": lead,
            "rows": ledger_rows(lead),
            "payment_form": payment_form,
            "ledger_form": ledger_form,
            "charge_form": charge_form,
        },
    )


def ledger_rows(lead):
    """One statement, charges and receipts in the order they happened.

    A charge raises what is owed and a payment lowers it, so both move the
    running balance in the last column. A charge is not money received and
    never belongs in the Received column — reading it there makes a customer
    who owes more look like a customer who has paid.
    """
    billed = lead.order_value or Decimal("0")
    received = Decimal("0")
    rows = []

    def add(date, label, charged, paid, entry=None, kind="payment"):
        rows.append(
            {
                "date": date,
                "label": label,
                "charged": charged,
                "amount": paid,
                "balance": billed - received,
                "entry": entry,
                "kind": kind,
            }
        )

    confirmed = timezone.localtime(lead.won_at).date() if lead.won_at else None
    add(confirmed, "Order confirmed", billed, None, kind="order")

    advance = lead.advance_received or Decimal("0")
    if advance:
        received += advance
        add(confirmed, "Advance received on order confirmation", None, advance, kind="advance")

    events = [(timezone.localtime(charge.added_at).date(), 0, charge) for charge in lead.invoice_charges.all()]
    events += [(payment.paid_on, 1, payment) for payment in lead.payments.all()]
    # Same-day charges are listed before the receipts that settle them.
    events.sort(key=lambda item: (item[0], item[1], item[2].pk))

    for date, _, entry in events:
        if isinstance(entry, InvoiceCharge):
            billed += entry.amount
            add(date, entry.description, entry.amount, None, entry, kind="charge")
        else:
            received += entry.amount
            add(date, entry.remarks or "Payment received", None, entry.amount, entry)

    return rows


@role_required(Role.ACCOUNTS)
def ledger_pdf(request, pk):
    """One customer's statement, as it reads on screen."""
    lead = get_object_or_404(
        Lead.objects.select_related("assigned_to").prefetch_related("payments", "invoice_charges"),
        pk=pk,
        status=Lead.Status.WON,
    )
    return render_customer_ledger(lead, ledger_rows(lead))


@role_required(Role.ACCOUNTS)
def outstanding_pdf(request):
    """Everything still owed, for chasing it — for the whole business, or one sales executive's customers."""
    leads = _orders()
    seller = _seller(request, order_sellers()) if request.GET.get("salesperson") else None
    if request.GET.get("salesperson") and seller is None:
        raise Http404("No confirmed orders belong to that sales executive.")
    if seller is not None:
        leads = leads.filter(credited_q(seller))
    return render_outstanding_statement(leads, request.GET.get("range"), seller=seller)


@role_required(Role.ACCOUNTS)
@require_POST
def payment_delete(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    lead_pk = payment.lead_id
    stored = [receipt.file for receipt in payment.receipts.all()]
    payment.delete()
    for file in stored:
        try:
            file.delete(save=False)
        except Exception:
            pass
    messages.success(request, "Payment entry removed.")
    return redirect("crm:ledger", pk=lead_pk)


@role_required(Role.ACCOUNTS)
@require_POST
def charge_delete(request, pk):
    charge = get_object_or_404(InvoiceCharge, pk=pk)
    lead_pk = charge.lead_id
    charge.delete()
    messages.success(request, "Charge removed from the invoice.")
    return redirect("crm:ledger", pk=lead_pk)


@role_required(Role.PRODUCTION)
def queue_production(request):
    # Sheets already uploaded wait on the measurement staff, not here; one sent back comes back here.
    leads = queues.production().select_related("assigned_to")
    return _queue(
        request, "crm/queues/simple.html", leads, "Production",
        "Orders waiting for a production sheet, and sheets sent back for changes.",
    )


FABRICATION_COLUMNS = [
    (Lead.Fabrication.FUTURE, "Future Production"),
    (Lead.Fabrication.UNDER, "Under Production"),
    (Lead.Fabrication.READY, "Ready for Dispatch"),
]


@role_required(Role.PRODUCTION)
def queue_fabrication(request):
    on_floor = queues.floor().select_related("assigned_to")
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
    # The same balance each row shows — extras billed and payments posted since
    # the advance count too — so the rows add up to the total.
    balance = sum(
        (lead.balance_amount or Decimal("0") for lead in queryset.prefetch_related("payments", "invoice_charges")),
        Decimal("0"),
    )
    return {
        "orders": figures["orders"] or 0,
        "windows": figures["windows"] or 0,
        "sqft": figures["sqft"] or 0,
        "value": value,
        "advance": advance,
        "balance": balance,
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
    leads = queues.handover().select_related("assigned_to")
    return _queue(
        request,
        "crm/queues/simple.html",
        leads,
        "Warranty & Handover",
        "Installed sites waiting for the signed handover certificate.",
    )


# ---------------------------------------------------------------------------
# notifications
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# to-do list (every role)
# ---------------------------------------------------------------------------


@login_required
def todo_list(request):
    mine = my_tasks(request.user)
    if request.GET.get("show") != "all":
        mine = mine.filter(done=False)

    if request.method == "POST":
        form = TaskForm(request.POST, user=request.user)
        if form.is_valid():
            task = form.save(commit=False)
            task.assigned_by = request.user
            task.save()
            if task.assigned_to_id != request.user.id:
                updates.send(
                    [task.assigned_to],
                    f"{request.user.display_name} assigned you: {task.title}",
                    topic=updates.todo(task),
                    link=updates.todo_link(),
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
            "assigned_by_me": Task.handed_out_by(request.user),
            "assigned_completed": Task.handed_out_by(request.user).filter(done=True).count(),
            "show_all": request.GET.get("show") == "all",
            "today": timezone.localdate(),
        },
    )


@login_required
@require_POST
def todo_done(request, pk):
    from .enquiries import complete_task

    task = get_object_or_404(Task, pk=pk, assigned_to=request.user)
    complete_task(task, request.user)
    return safe_next(request, reverse("crm:todo_list"))


REMIND_AGAIN_AFTER = timedelta(minutes=30)


@login_required
@require_POST
def todo_remind(request, pk):
    """Nudge the person an overdue to-do was assigned to, with an alert and a phone banner."""
    task = get_object_or_404(Task.objects.select_related("assigned_to"), pk=pk, assigned_by=request.user)
    back = safe_next(request, reverse("crm:todo_list") + "#assigned")
    if task.assigned_to_id == request.user.id or not task.is_overdue:
        messages.error(request, "A reminder can only be sent for an overdue to-do assigned to someone else.")
        return back
    # Pressing it twice in a row would only pile alerts onto the same phone.
    recent = Notification.objects.filter(
        topic=updates.todo(task), message__startswith="Reminder", created_at__gte=timezone.now() - REMIND_AGAIN_AFTER
    )
    if recent.exists():
        messages.info(request, f"{task.assigned_to} was reminded a moment ago.")
        return back
    days = (timezone.localdate() - task.due_date).days
    late = "due yesterday" if days == 1 else f"overdue by {days} days"
    # The same topic as the assignment, so completing the to-do clears the reminder too;
    # today's replaces the earlier alert rather than sitting beside it.
    updates.clear(updates.todo(task), user=task.assigned_to)
    updates.send(
        [task.assigned_to],
        f"Reminder from {request.user.display_name}: {task.title} is {late}",
        topic=updates.todo(task),
        link=updates.todo_link(),
    )
    messages.success(request, f"Reminder sent to {task.assigned_to}.")
    return back


@login_required
@require_POST
def todo_clear(request, pk=None):
    """Clear completed to-dos off your "Assigned by me" list — one, or every completed one."""
    finished = Task.objects.filter(assigned_by=request.user, done=True, cleared_by_assigner_at__isnull=True)
    if pk is not None:
        finished = finished.filter(pk=pk)
    cleared = list(finished)
    Task.objects.filter(pk__in=[task.pk for task in cleared]).update(cleared_by_assigner_at=timezone.now())
    # The "completed" update has said all it had to.
    if cleared:
        updates.clear(*[updates.todo_finished(task) for task in cleared], user=request.user)
    return safe_next(request, reverse("crm:todo_list") + "#assigned")


@login_required
@require_POST
def todo_delete(request, pk):
    task = get_object_or_404(Task, pk=pk, assigned_by=request.user)
    updates.clear(updates.todo(task), updates.todo_finished(task))
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
    notify(lead, f"Service complaint raised - {lead.customer_name}: {complaint.description}",
           Role.FIELD_MANAGER, Role.SUPER_ADMIN, topic=updates.complaint(complaint), link=updates.complaints_link())
    messages.success(request, "Service complaint registered.")
    return safe_next(request, reverse("crm:completed_projects"))


@role_required(Role.SALESPERSON, Role.FIELD_MANAGER)
@require_POST
def complaint_register(request):
    """The Service Requests page's form: the project is picked from a list, not the address."""
    try:
        pk = int(request.POST.get("lead", ""))
    except ValueError:
        messages.error(request, "Choose the completed project the complaint is about.")
        return redirect("crm:complaint_list")
    return complaint_create(request, pk)


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
    if not complaint.is_open:  # a second tap, or someone else got there first
        messages.info(request, "That complaint is already resolved.")
        return redirect("crm:complaint_list")
    form = ComplaintResolveForm(request.POST, instance=complaint)
    if not form.is_valid():
        messages.error(request, form_problems(form))
        return redirect("crm:complaint_list")
    complaint = form.save(commit=False)
    complaint.resolution_note = complaint.resolution_note.strip()
    complaint.resolved_at = timezone.now()
    complaint.resolved_by = request.user
    complaint.save()
    updates.clear(updates.complaint(complaint))
    notify_user(complaint.lead, f"Service complaint resolved - {complaint.lead.customer_name}", complaint.raised_by,
                link=updates.completed_link(complaint.lead))
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
    items = list(request.user.notifications.filter(cleared=False).select_related("lead")[:100])
    request.user.notifications.filter(read=False).update(read=True)
    return render(request, "crm/notifications.html", {"notifications": items})


@login_required
@require_POST
def notification_clear(request, pk):
    """Take one notification off your own list. It also stops counting and popping up."""
    request.user.notifications.filter(pk=pk).update(cleared=True, read=True, dismissed=True, popped=True)
    return safe_next(request, reverse("crm:notifications"))


# ---------------------------------------------------------------------------
# walkthrough
# ---------------------------------------------------------------------------


def _guide_context(request):
    """The intro scenes and the tour, both built for whoever is signed in."""
    nav_groups = navigation(request, take_popups=False).get("nav_groups", [])
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


# ---------------------------------------------------------------------------
# summary for the day
# ---------------------------------------------------------------------------


def _summary_day(request):
    """The day being looked at — today unless one is asked for."""
    asked = request.GET.get("day")
    if asked:
        try:
            parsed = parse_date(asked)
        except ValueError:  # a real-looking date that does not exist, like 30 February
            parsed = None
        if parsed and parsed <= timezone.localdate():
            return parsed
    return timezone.localdate()


@role_required(Role.SUPER_ADMIN)
def day_summary(request):
    day = _summary_day(request)
    people = User.objects.filter(is_active=True).exclude(pk=request.user.pk)
    return render(
        request,
        "crm/day_summary.html",
        {
            "day": day,
            "is_today": day == timezone.localdate(),
            "rows": daysummary.counts_for(people, day),
        },
    )


@role_required(Role.SUPER_ADMIN)
def month_summary(request):
    """The month in numbers, for any month. Also where marketing spend is entered."""
    if request.method == "POST":
        first = monthly.parse_month(request.POST.get("month"))
        monthly.save_spend(first, request.POST)
        messages.success(request, f"What was spent in {first:%B %Y} is saved.")
        return redirect(f"{reverse('crm:month_summary')}?month={first:%Y-%m}")

    first = monthly.parse_month(request.GET.get("month"))
    data = monthly.report(first)
    # Opening it is what the month-end reminder asked for.
    updates.clear(updates.month(first), user=request.user)

    # Every month from the first lead to this one, newest first, for the picker.
    months, cursor, this_month = [], monthly.first_month_with_data(), monthly.month_start(timezone.localdate())
    while cursor <= this_month:
        months.append(cursor)
        cursor = monthly.next_month(cursor)
    months.reverse()

    spent = {row["key"]: row["spend"] for row in data["sources"] if row["spend"]}
    return render(
        request,
        "crm/month_summary.html",
        {
            "m": data,
            "months": months,
            "spend_rows": [(key, label, spent.get(key, "")) for key, label in Lead.LEAD_SOURCES],
        },
    )


@role_required(Role.SUPER_ADMIN)
def day_summary_person(request, pk):
    day = _summary_day(request)
    person = get_object_or_404(User, pk=pk, is_active=True)
    return render(
        request,
        "crm/day_summary_person.html",
        {
            "day": day,
            "is_today": day == timezone.localdate(),
            "person": person,
            **daysummary.for_person(person, day),
        },
    )
