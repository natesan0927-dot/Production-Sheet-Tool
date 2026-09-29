"""The Installation section, under Production.

Installation is outsourced. Production names the installer when a site goes out;
the site then waits under "Awaiting Installation" until someone marks it
installed, and handover opens after that. What the installer is owed is their
rate per sq ft times the site's sq ft, and the Installation Ledger keeps a folder
per installer with a ledger per site for paying it off.

Who works it: production, the Super Admin, and anyone the Super Admin gives the
Installation step to under Stage Access (see stages.can_act).
"""

from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from apps.accounts.models import Role

from . import installation, queues, updates
from . import stages as stage_flow
from .forms import InstallationRateForm, InstallerChargeForm, InstallerPaymentForm, installation_total
from .models import InstallerCharge, InstallerPayment, InstallerReceipt, Lead, plain
from .reminders import INSTALL_LATE_AFTER_DAYS
from .views import download, notify, safe_next

# A site not marked installed this many days after dispatch is chased (see reminders.py).
LATE_AFTER_DAYS = INSTALL_LATE_AFTER_DAYS


def installation_access(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not stage_flow.can_act(request.user, stage_flow.INSTALLATION):
            return HttpResponseForbidden("Installation is not one of your steps.")
        return view(request, *args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# awaiting installation
# ---------------------------------------------------------------------------


@installation_access
def installation_pending(request):
    """Every dispatched site not yet marked installed, oldest first, late ones flagged."""
    today = timezone.localdate()
    sites = []
    for lead in queues.installation().select_related("assigned_to").order_by("dispatched_at", "pk"):
        dispatched_on = timezone.localtime(lead.dispatched_at).date()
        days = (today - dispatched_on).days
        sites.append({"lead": lead, "dispatched_on": dispatched_on, "days": days, "late": days >= LATE_AFTER_DAYS})
    return render(
        request,
        "crm/installation/pending.html",
        {"sites": sites, "today": today, "late_after": LATE_AFTER_DAYS},
    )


def _completion_date(request, lead):
    """The day the site was finished: today unless another day is given, never before dispatch."""
    typed = request.POST.get("completed_on", "")
    try:
        day = parse_date(typed) if typed else None
    except ValueError:
        day = None
    day = day or timezone.localdate()
    dispatched_on = timezone.localtime(lead.dispatched_at).date()
    if day > timezone.localdate():
        return None, "The installation can't be finished in the future."
    if day < dispatched_on:
        return None, f"The installation can't be finished before the site was dispatched ({dispatched_on:%d %b %Y})."
    return day, None


@installation_access
@require_POST
def installation_complete(request, pk):
    lead = get_object_or_404(Lead, pk=pk, status=Lead.Status.WON)
    back = reverse("crm:installation_pending")
    if not lead.dispatched_at:
        messages.error(request, "This site has not been dispatched yet.")
        return safe_next(request, back)
    if lead.installation_completed_on:
        messages.info(request, f"{lead.customer_name} is already marked installed.")
        return safe_next(request, back)

    day, problem = _completion_date(request, lead)
    if problem:
        messages.error(request, problem)
        return safe_next(request, back)

    lead.installation_completed_on = day
    lead.installation_completed_at = timezone.now()
    lead.installation_completed_by = request.user
    lead.save(update_fields=["installation_completed_on", "installation_completed_at", "installation_completed_by", "updated_at"])
    updates.clear(updates.INSTALL, lead=lead)
    notify(lead, f"Installation complete — handover pending for {lead.customer_name}",
           Role.FIELD_MANAGER, topic=updates.HANDOVER)
    messages.success(request, f"{lead.customer_name} marked installed. Handover is now open for the field manager.")
    return safe_next(request, back)


@installation_access
@require_POST
def installation_reopen(request, pk):
    """Undo a site marked installed by mistake — only until its handover is under way."""
    lead = get_object_or_404(Lead, pk=pk, status=Lead.Status.WON)
    if lead.handover_signed_at or lead.completed_at:
        messages.error(request, "The handover has already been signed, so the installation stays complete.")
        return safe_next(request, lead.get_absolute_url())
    lead.installation_completed_on = None
    lead.installation_completed_at = None
    lead.installation_completed_by = None
    lead.installation_reminded_on = None
    lead.save(update_fields=["installation_completed_on", "installation_completed_at", "installation_completed_by",
                             "installation_reminded_on", "updated_at"])
    # The field manager was told it was ready; it is not any more.
    updates.clear(updates.HANDOVER, lead=lead)
    messages.success(request, f"{lead.customer_name} is back to awaiting installation.")
    return safe_next(request, lead.get_absolute_url())


# ---------------------------------------------------------------------------
# the installation ledger
# ---------------------------------------------------------------------------


@installation_access
def installation_list(request):
    """A folder for each installer, named after them."""
    query = request.GET.get("q", "").strip()
    everyone = installation.folders()
    folders = installation.matching(everyone, query)
    return render(
        request,
        "crm/installation/folders.html",
        {
            "folders": folders,
            "q": query,
            "owed": sum((folder["balance"] for folder in everyone), Decimal("0")),
            "sites": sum(folder["sites"] for folder in everyone),
            "installers": len(everyone),
            "unpriced": sum(folder["unpriced"] for folder in everyone),
        },
    )


@installation_access
def installer_sites(request, slug):
    """One installer's sites, laid out like a ledger."""
    folder = installation.folder(slug)
    if folder is None:
        raise Http404
    return render(request, "crm/installation/sites.html", {"folder": folder})


def _site(pk):
    """A dispatched site that has an installer, or a 404."""
    lead = get_object_or_404(
        Lead.objects.select_related("assigned_to").prefetch_related("installer_payments__receipts", "installer_charges"),
        pk=pk,
        status=Lead.Status.WON,
        dispatched_at__isnull=False,
    )
    if not lead.installation_person:
        raise Http404
    return lead


def _ledger_rows(lead):
    """The charge first, then what was added and paid in date order, with the balance after each.

    An addition raises what is owed and a payment lowers it. Additions come
    before same-day payments, so a payment never shows the installer as overpaid
    when the extra it settles was added that morning.
    """
    rows = []
    charge = lead.installation_charge
    balance = Decimal("0")
    if charge is not None:
        if lead.installation_rate and lead.total_sqft:
            label = f"Installation charge: ₹{lead.installation_rate:,.2f} per sq ft × {plain(lead.total_sqft)} sq ft"
        else:
            label = "Installation charge agreed"
        balance = charge
        rows.append({"date": timezone.localtime(lead.dispatched_at).date(), "label": label, "payable": charge,
                     "paid": None, "balance": balance, "entry": None, "kind": "charge"})

    events = [(extra.added_on, 0, extra.pk, extra) for extra in lead.installer_charges.all()]
    events += [(payment.paid_on, 1, payment.pk, payment) for payment in lead.installer_payments.all()]
    for day, order, _, entry in sorted(events, key=lambda item: item[:3]):
        if order == 0:
            balance += entry.amount
            rows.append({"date": day, "label": entry.description, "payable": entry.amount, "paid": None,
                         "balance": balance, "entry": entry, "kind": "extra"})
        else:
            balance -= entry.amount
            rows.append({"date": day, "label": entry.remarks or "Payment to installer", "payable": None,
                         "paid": entry.amount, "balance": balance, "entry": entry, "kind": "payment"})
    return rows


@installation_access
def installer_ledger(request, pk):
    """A site's ledger with its installer: what is owed, what has been paid, what is left."""
    lead = _site(pk)
    payment_form = InstallerPaymentForm(lead=lead)
    rate_form = InstallationRateForm(instance=lead)
    extra_form = InstallerChargeForm()

    if request.method == "POST":
        if "add_payable" in request.POST:
            extra_form = InstallerChargeForm(request.POST)
            if extra_form.is_valid():
                extra = extra_form.save(commit=False)
                extra.lead = lead
                extra.recorded_by = request.user
                extra.save()
                messages.success(
                    request, f"₹{extra.amount:,.2f} added to what {lead.installation_person} is owed for this site."
                )
                return redirect("crm:installer_ledger", pk=lead.pk)
        elif "save_rate" in request.POST:
            rate_form = InstallationRateForm(request.POST, instance=Lead.objects.get(pk=lead.pk))
            if rate_form.is_valid():
                site = rate_form.save(commit=False)
                site.installation_charge = installation_total(site.installation_rate, site.total_sqft)
                site.save(update_fields=["installation_rate", "total_sqft", "installation_charge", "updated_at"])
                messages.success(
                    request,
                    f"₹{site.installation_rate:,.2f} per sq ft × {plain(site.total_sqft)} sq ft — "
                    f"₹{site.installation_charge:,.2f} payable to {site.installation_person}.",
                )
                return redirect("crm:installer_ledger", pk=lead.pk)
        else:
            payment_form = InstallerPaymentForm(request.POST, request.FILES, lead=lead)
            if payment_form.is_valid():
                payment = payment_form.save(commit=False)
                payment.lead = lead
                payment.recorded_by = request.user
                payment.save()
                for upload in payment_form.cleaned_data["files"]:
                    InstallerReceipt.objects.create(payment=payment, file=upload)
                messages.success(request, "Payment to the installer posted.")
                return redirect("crm:installer_ledger", pk=lead.pk)

    return render(
        request,
        "crm/installation/ledger.html",
        {
            "lead": lead,
            "rows": _ledger_rows(lead),
            "payment_form": payment_form,
            "rate_form": rate_form,
            "extra_form": extra_form,
            "folder_slug": installation.folder_slug_for(lead),
        },
    )


@installation_access
@require_POST
def installer_charge_delete(request, pk):
    """Take back something added to the payable — unless it would leave the installer overpaid."""
    extra = get_object_or_404(InstallerCharge.objects.select_related("lead"), pk=pk)
    lead = extra.lead
    if (lead.installer_balance or Decimal("0")) - extra.amount < 0:
        messages.error(
            request,
            f"₹{lead.installer_paid:,.2f} has already been paid against this site, so removing this "
            "would leave the installer overpaid. Remove the payment first.",
        )
        return redirect("crm:installer_ledger", pk=lead.pk)
    extra.delete()
    messages.success(request, f"{extra.description} removed from the payable.")
    return redirect("crm:installer_ledger", pk=lead.pk)


@installation_access
@require_POST
def installer_payment_delete(request, pk):
    payment = get_object_or_404(InstallerPayment, pk=pk)
    lead_pk = payment.lead_id
    stored = [receipt.file for receipt in payment.receipts.all()]
    payment.delete()
    for file in stored:
        try:
            file.delete(save=False)
        except Exception:
            pass
    messages.success(request, "Payment removed.")
    return redirect("crm:installer_ledger", pk=lead_pk)


@installation_access
def installer_receipt(request, pk):
    receipt = get_object_or_404(InstallerReceipt, pk=pk)
    return download(receipt.file)

