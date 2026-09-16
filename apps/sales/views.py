from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from apps.core.mixins import RoleRequiredMixin
from apps.core.models import LeadStatus
from apps.core.notifications import notify, notify_many
from apps.crm.models import Lead
from apps.sales.forms import OrderConfirmForm, PaymentForm, QuotationForm, QuotationItemFormSet, QuotationReviseForm, SalesTargetForm
from apps.sales.models import CustomerAcquisitionForm, Order, OrderItem, Payment, Quotation, SalesTarget


# ---------------------------------------------------------------------------
# Quotations
# ---------------------------------------------------------------------------
class QuotationListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    section = "crm_sales"
    model = Quotation
    template_name = "sales/quotation_list.html"
    context_object_name = "quotations"
    paginate_by = 30

    def get_queryset(self):
        qs = Quotation.objects.select_related("customer", "lead").order_by("-created_at")
        if not self.request.user.has_role("Super Admin", "Management", "Sales Manager", "Quotation Staff", "Admin Staff"):
            qs = qs.filter(lead__assigned_salesperson=self.request.user)
        return qs


class QuotationDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    section = "crm_sales"
    model = Quotation
    template_name = "sales/quotation_detail.html"
    context_object_name = "quotation"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["all_versions"] = Quotation.objects.filter(root_number=self.object.root_number).order_by("version")
        return ctx


@login_required
@require_POST
def quotation_request(request, lead_pk):
    """
    The salesperson's "Request Quotation" action (spec section 11): flags the
    lead as needing a quotation and notifies the Quotation Staff team, without
    requiring the salesperson to fill in pricing themselves. Anyone with
    access can still open "Create Quotation" directly from the lead page.
    """
    lead = get_object_or_404(Lead, pk=lead_pk)
    pending_status = LeadStatus.objects.filter(name__icontains="Quotation Pending").first()
    if pending_status:
        lead.status = pending_status
        lead.save(update_fields=["status"])

    from apps.accounts.models import User

    quotation_staff = User.objects.filter(groups__name__in=["Quotation Staff", "Super Admin"], is_active=True).distinct()
    notify_many(
        quotation_staff, f"Quotation requested for {lead.lead_id}",
        url=lead.get_absolute_url(), related_object=lead,
    )
    messages.success(request, "Quotation team notified.")
    return redirect("crm:lead_detail", pk=lead_pk)


@login_required
def quotation_create(request):
    lead_id = request.GET.get("lead")
    lead = get_object_or_404(Lead, pk=lead_id) if lead_id else None
    quotation = Quotation(lead=lead, customer=lead.customer if lead else None, prepared_by=request.user)
    if lead:
        quotation.warranty_text = ""

    if request.method == "POST":
        form = QuotationForm(request.POST, instance=quotation)
        formset = QuotationItemFormSet(request.POST, instance=quotation)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                quotation = form.save(commit=False)
                quotation.lead = lead
                quotation.customer = lead.customer
                quotation.prepared_by = request.user
                if not quotation.warranty_text:
                    from apps.core.models import CompanyProfile
                    quotation.warranty_text = CompanyProfile.load().default_warranty_terms
                if not quotation.terms_text:
                    from apps.core.models import CompanyProfile
                    quotation.terms_text = CompanyProfile.load().default_quotation_terms
                quotation.save()
                formset.instance = quotation
                formset.save()
                quotation.recalculate_totals()

                sent_status = LeadStatus.objects.filter(name__icontains="Quotation Sent").first()
                if sent_status:
                    lead.status = sent_status
                    lead.save(update_fields=["status"])

                if lead.assigned_salesperson:
                    notify(
                        lead.assigned_salesperson, f"Quotation {quotation.quotation_number} is ready",
                        url=quotation.get_absolute_url(), related_object=quotation,
                    )
            messages.success(request, f"Quotation {quotation.quotation_number} created.")
            return redirect(f"{reverse('sales:quotation_detail', args=[quotation.pk])}?autoexport=1")
    else:
        form = QuotationForm(instance=quotation)
        formset = QuotationItemFormSet(instance=quotation)

    return render(request, "sales/quotation_form.html", {"form": form, "formset": formset, "lead": lead})


@login_required
@require_POST
def quotation_revise(request, pk):
    original = get_object_or_404(Quotation, pk=pk)
    form = QuotationReviseForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            new_version = Quotation.objects.create(
                root_number=original.root_number,
                version=Quotation.objects.filter(root_number=original.root_number).count() + 1,
                lead=original.lead, customer=original.customer,
                payment_terms=original.payment_terms, delivery_period=original.delivery_period,
                warranty_text=original.warranty_text, terms_text=original.terms_text,
                tax_percent=original.tax_percent, prepared_by=request.user,
                revised_from=original, revision_reason=form.cleaned_data["reason"],
            )
            for item in original.items.all():
                item.pk = None
                item.quotation = new_version
                item.save()
            new_version.recalculate_totals()
            original.status = "superseded"
            original.save(update_fields=["status"])

            if original.lead.assigned_salesperson:
                notify(
                    original.lead.assigned_salesperson, f"Quotation revised: {new_version.quotation_number}",
                    url=new_version.get_absolute_url(), related_object=new_version,
                )
        messages.success(request, f"Created revision {new_version.quotation_number}.")
        return redirect("sales:quotation_detail", pk=new_version.pk)
    messages.error(request, "Please provide a reason for the revision.")
    return redirect("sales:quotation_detail", pk=pk)


@login_required
@require_POST
def quotation_send(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)
    quotation.status = "sent"
    quotation.save(update_fields=["status"])
    messages.success(request, "Quotation marked as sent to customer.")
    return redirect(f"{reverse('sales:quotation_detail', args=[pk])}?autoexport=1")


# ---------------------------------------------------------------------------
# Orders (WON workflow) / Customer Acquisition Form
# ---------------------------------------------------------------------------
class OrderListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    section = "crm_sales"
    model = Order
    template_name = "sales/order_list.html"
    context_object_name = "orders"
    paginate_by = 30

    def get_queryset(self):
        qs = Order.objects.select_related("customer", "salesperson").order_by("-confirmed_at")
        if not self.request.user.has_role("Super Admin", "Management", "Sales Manager", "Admin Staff", "Production Manager"):
            qs = qs.filter(salesperson=self.request.user)
        return qs


class OrderDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    section = "crm_sales"
    model = Order
    template_name = "sales/order_detail.html"
    context_object_name = "order"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        order = self.object
        ctx["payment_form"] = PaymentForm()
        ctx["timeline"] = build_order_timeline(order)
        return ctx


def build_order_timeline(order):
    events = [{"label": "Order Confirmed", "date": order.confirmed_at, "done": True}]
    if hasattr(order, "acquisition_form"):
        events.append({"label": "Customer Acquisition Form Generated", "date": order.acquisition_form.generated_at, "done": True})
    else:
        events.append({"label": "Customer Acquisition Form", "date": None, "done": False})
    fm = order.final_measurements.first()
    events.append({"label": "Final Measurement", "date": fm.completed_at if fm else None, "done": bool(fm and fm.status == "approved")})
    sheet = getattr(order, "production_sheet", None)
    events.append({"label": "Production Sheet Approved", "date": sheet.approved_at if sheet else None, "done": bool(sheet and sheet.status == "approved")})
    events.append({"label": "Production Completed", "date": None, "done": bool(sheet and sheet.status == "completed")})
    dispatch = getattr(order, "dispatch", None)
    events.append({"label": "Dispatched", "date": dispatch.dispatch_date if dispatch else None, "done": bool(dispatch)})
    installation = getattr(order, "installation", None)
    events.append({"label": "Installed", "date": installation.actual_date if installation else None, "done": bool(installation and installation.status == "completed")})
    handover = getattr(installation, "handover", None) if installation else None
    events.append({"label": "Handed Over", "date": handover.installation_date if handover else None, "done": bool(handover)})
    events.append({"label": "Warranty Activated", "date": None, "done": hasattr(order, "warranty")})
    return events


@login_required
def order_create(request):
    lead_id = request.GET.get("lead")
    lead = get_object_or_404(Lead, pk=lead_id)
    quotation = lead.quotations.exclude(status="superseded").order_by("-version").first()
    if not quotation:
        messages.error(request, "A quotation must exist before this lead can be marked as Won.")
        return redirect("crm:lead_detail", pk=lead.pk)
    if hasattr(lead, "order"):
        messages.info(request, "This lead already has an order.")
        return redirect("sales:order_detail", pk=lead.order.pk)

    initial = {
        "final_order_value": quotation.total_value,
        "discount": quotation.discount,
        "tax": quotation.tax_amount,
        "payment_terms": quotation.payment_terms_id,
    }

    if request.method == "POST":
        form = OrderConfirmForm(request.POST, initial=initial)
        if form.is_valid():
            with transaction.atomic():
                order = form.save(commit=False)
                order.lead = lead
                order.customer = lead.customer
                order.quotation = quotation
                order.confirmed_quotation_version = quotation.version
                order.original_quotation_value = quotation.total_value
                order.final_value = form.cleaned_data["final_order_value"] - form.cleaned_data["discount"] + form.cleaned_data["tax"]
                order.balance_amount = order.final_value - form.cleaned_data["advance_amount"]
                order.salesperson = lead.assigned_salesperson or request.user
                order.save()

                for item in quotation.items.all():
                    OrderItem.objects.create(
                        order=order, description=item.description, dimensions=item.dimensions,
                        quantity=item.quantity, unit_rate=item.unit_rate, amount=item.amount,
                        glass=item.glass, hardware=item.hardware, accessories=item.accessories,
                    )

                quotation.status = "won"
                quotation.save(update_fields=["status"])

                won_status = LeadStatus.objects.filter(is_won=True).first()
                if won_status:
                    lead.status = won_status
                    lead.save(update_fields=["status"])

                from apps.sales.services import generate_customer_acquisition_form
                generate_customer_acquisition_form(order, request.user)

            messages.success(request, f"Order {order.order_number} confirmed. Customer Acquisition Form generated.")
            return redirect(f"{reverse('sales:order_detail', args=[order.pk])}?autoexport=1")
    else:
        form = OrderConfirmForm(initial=initial)

    return render(request, "sales/order_confirm_form.html", {"form": form, "lead": lead, "quotation": quotation})


@login_required
@require_POST
def payment_add(request, pk):
    order = get_object_or_404(Order, pk=pk)
    form = PaymentForm(request.POST)
    if form.is_valid():
        payment = form.save(commit=False)
        payment.order = order
        payment.recorded_by = request.user
        payment.save()
        messages.success(request, "Payment recorded.")
    else:
        messages.error(request, "Please correct the payment details.")
    return redirect("sales:order_detail", pk=pk)


@login_required
def caf_regenerate(request, pk):
    order = get_object_or_404(Order, pk=pk)
    from apps.sales.services import generate_customer_acquisition_form

    caf = generate_customer_acquisition_form(order, request.user)
    messages.success(request, f"Customer Acquisition Form regenerated (v{caf.version}).")
    return redirect(f"{reverse('sales:order_detail', args=[order.pk])}?autoexport=1")


# ---------------------------------------------------------------------------
# Sales targets
# ---------------------------------------------------------------------------
class TargetListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    section = "crm_sales"
    model = SalesTarget
    template_name = "sales/target_list.html"
    context_object_name = "targets"

    def get_queryset(self):
        qs = SalesTarget.objects.select_related("salesperson").order_by("-year", "-month")
        if not self.request.user.has_role("Super Admin", "Management", "Sales Manager", "Admin Staff"):
            qs = qs.filter(salesperson=self.request.user)
        return qs


@login_required
def target_create(request):
    if request.method == "POST":
        form = SalesTargetForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Sales target saved.")
            return redirect("sales:target_list")
    else:
        form = SalesTargetForm()
    return render(request, "sales/target_form.html", {"form": form})
