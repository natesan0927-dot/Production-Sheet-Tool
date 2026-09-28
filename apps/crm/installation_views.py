"""The Installation section: a folder per installer, and a ledger per site.

Installation is outsourced. Production names the installer when a site goes out;
accounts agrees what that installer is owed for the site and pays it off in
instalments. This is where that is seen and posted.
"""

from decimal import Decimal

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import Role

from . import installation
from .forms import InstallationChargeForm, InstallerPaymentForm
from .models import InstallerPayment, Lead
from .views import role_required


@role_required(Role.ACCOUNTS)
def installation_list(request):
    """A folder for each installer, named after them."""
    query = request.GET.get("q", "").strip()
    folders = installation.folders(query)
    everyone = installation.folders()
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


@role_required(Role.ACCOUNTS)
def installer_sites(request, slug):
    """One installer's sites, laid out like a ledger."""
    folder = installation.folder(slug)
    if folder is None:
        raise Http404
    return render(request, "crm/installation/sites.html", {"folder": folder})


def _site(pk):
    """A dispatched site that has an installer, or a 404."""
    lead = get_object_or_404(
        Lead.objects.select_related("assigned_to").prefetch_related("installer_payments"),
        pk=pk,
        status=Lead.Status.WON,
        dispatched_at__isnull=False,
    )
    if not lead.installation_person:
        raise Http404
    return lead


def _ledger_rows(lead):
    """The charge first, then every payment, with the balance still owed after each."""
    rows = []
    charge = lead.installation_charge
    if charge is not None:
        rows.append({"date": lead.dispatched_at, "label": "Installation charge agreed", "payable": charge, "paid": None, "balance": charge, "entry": None})
    balance = charge
    for payment in lead.installer_payments.all():
        balance = (balance - payment.amount) if balance is not None else None
        rows.append({"date": payment.paid_on, "label": payment.remarks or "Payment to installer", "payable": None, "paid": payment.amount, "balance": balance, "entry": payment})
    return rows


@role_required(Role.ACCOUNTS)
def installer_ledger(request, pk):
    """A site's ledger with its installer: what is owed, what has been paid, what is left."""
    lead = _site(pk)
    payment_form = InstallerPaymentForm(lead=lead)
    charge_form = InstallationChargeForm(instance=lead)

    if request.method == "POST":
        if "save_charge" in request.POST:
            charge_form = InstallationChargeForm(request.POST, instance=lead)
            if charge_form.is_valid():
                charge_form.save()
                messages.success(request, "The total payable to the installer is saved.")
                return redirect("crm:installer_ledger", pk=lead.pk)
        else:
            payment_form = InstallerPaymentForm(request.POST, request.FILES, lead=lead)
            if payment_form.is_valid():
                payment = payment_form.save(commit=False)
                payment.lead = lead
                payment.recorded_by = request.user
                payment.save()
                messages.success(request, "Payment to the installer posted.")
                return redirect("crm:installer_ledger", pk=lead.pk)

    return render(
        request,
        "crm/installation/ledger.html",
        {
            "lead": lead,
            "rows": _ledger_rows(lead),
            "payment_form": payment_form,
            "charge_form": charge_form,
            "folder_slug": installation.folder_slug_for(lead),
        },
    )


@role_required(Role.ACCOUNTS)
@require_POST
def installer_payment_delete(request, pk):
    payment = get_object_or_404(InstallerPayment, pk=pk)
    lead_pk = payment.lead_id
    payment.delete()
    messages.success(request, "Payment removed.")
    return redirect("crm:installer_ledger", pk=lead_pk)
