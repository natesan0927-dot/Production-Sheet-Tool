from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.core.mixins import AutoLocalExportMixin, RoleRequiredMixin
from apps.core.models import LeadStatus
from apps.core.notifications import notify
from apps.crm.forms import CustomerForm, FollowUpForm, LeadAssignForm, LeadCreateForm, LeadUpdateForm, LostLeadForm
from apps.crm.models import Customer, FollowUp, Lead, LeadAssignment, LostLeadDetail


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
class CustomerListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    section = "crm_sales"
    model = Customer
    template_name = "crm/customer_list.html"
    context_object_name = "customers"
    paginate_by = 30

    def get_queryset(self):
        qs = Customer.objects.select_related("assigned_salesperson").order_by("-created_date")
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(
                Q(customer_name__icontains=q) | Q(mobile_number__icontains=q) |
                Q(customer_code__icontains=q) | Q(project_name__icontains=q)
            )
        if not self.request.user.has_role("Super Admin", "Management", "Sales Manager", "Admin Staff"):
            qs = qs.filter(assigned_salesperson=self.request.user)
        return qs


class CustomerDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    section = "crm_sales"
    """Customer 360 view: everything about the customer in one place."""

    model = Customer
    template_name = "crm/customer_detail.html"
    context_object_name = "customer"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        customer = self.object
        ctx["leads"] = customer.leads.select_related("status").order_by("-created_date")
        ctx["communications"] = customer.communications.all()[:25]
        orders = getattr(customer, "orders", None)
        ctx["orders"] = orders.all() if orders is not None else []
        return ctx


class CustomerCreateView(LoginRequiredMixin, AutoLocalExportMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = "crm/customer_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Customer {self.object.customer_code} created.")
        return response

    def get_success_url(self):
        return reverse("crm:customer_detail", args=[self.object.pk])


class CustomerUpdateView(LoginRequiredMixin, AutoLocalExportMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = "crm/customer_form.html"

    def get_success_url(self):
        return reverse("crm:customer_detail", args=[self.object.pk])


@login_required
def customer_lookup(request):
    """
    Looks up a customer by (partial) mobile number while a rep is filling in
    the Add Lead form, so the same person's details are never re-entered --
    this is what drives the "one combined step" lead-creation flow.
    """
    mobile = request.GET.get("mobile", "").strip()
    if len(mobile) < 6:
        return JsonResponse({"found": False})
    customer = Customer.objects.filter(mobile_number__icontains=mobile).order_by("-created_date").first()
    if not customer:
        return JsonResponse({"found": False})
    return JsonResponse({
        "found": True,
        "id": customer.pk,
        "name": customer.customer_name,
        "code": customer.customer_code,
        "mobile": customer.mobile_number,
        "email": customer.email,
        "project_name": customer.project_name,
    })


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------
class LeadListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    section = "crm_sales"
    model = Lead
    template_name = "crm/lead_list.html"
    context_object_name = "leads"
    paginate_by = 30

    def get_queryset(self):
        qs = Lead.objects.select_related("customer", "status", "assigned_salesperson").order_by("-created_date")
        q = self.request.GET.get("q")
        status = self.request.GET.get("status")
        if q:
            qs = qs.filter(Q(lead_id__icontains=q) | Q(customer__customer_name__icontains=q) | Q(project_name__icontains=q))
        if status:
            qs = qs.filter(status_id=status)
        if not self.request.user.has_role("Super Admin", "Management", "Sales Manager", "Admin Staff"):
            qs = qs.filter(assigned_salesperson=self.request.user)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["statuses"] = LeadStatus.objects.all()
        return ctx


class LeadDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    section = "crm_sales"
    model = Lead
    template_name = "crm/lead_detail.html"
    context_object_name = "lead"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        lead = self.object
        ctx["followups"] = lead.followups.all()
        ctx["followup_form"] = FollowUpForm()
        ctx["assign_form"] = LeadAssignForm(initial={"assigned_to": lead.assigned_salesperson_id})
        ctx["quotations"] = getattr(lead, "quotations", None).all() if hasattr(lead, "quotations") else []
        ctx["measurement_requests"] = getattr(lead, "measurement_requests", None).all() if hasattr(lead, "measurement_requests") else []
        ctx["active_measurement_request"] = lead.measurement_requests.exclude(status="cancelled").first()
        ctx["timeline"] = build_lead_timeline(lead)
        return ctx


def build_lead_timeline(lead):
    events = [{"label": "Lead Created", "date": lead.created_date, "done": True}]
    for a in lead.assignments.all():
        events.append({"label": f"Assigned to {a.assigned_to}", "date": a.assigned_at, "done": True})
    for m in getattr(lead, "measurement_requests", Lead.objects.none()).all() if hasattr(lead, "measurement_requests") else []:
        events.append({"label": f"Measurement {m.get_status_display()}", "date": m.requested_date, "done": True})
    for f in lead.followups.all():
        events.append({"label": f"Follow-up: {f.get_type_display()}", "date": f.date, "done": True})
    if hasattr(lead, "quotations"):
        for qn in lead.quotations.all():
            events.append({"label": f"Quotation {qn.quotation_number} ({qn.get_status_display()})", "date": qn.created_at, "done": True})
    if lead.is_won:
        events.append({"label": "Lead Won", "date": None, "done": True})
    if lead.is_lost:
        events.append({"label": "Lead Lost", "date": None, "done": True})
    return events


class LeadCreateView(LoginRequiredMixin, AutoLocalExportMixin, CreateView):
    model = Lead
    form_class = LeadCreateForm
    template_name = "crm/lead_form.html"

    def get_initial(self):
        initial = super().get_initial()
        customer_id = self.request.GET.get("customer")
        if customer_id:
            initial["customer"] = customer_id
        return initial

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f"Lead {self.object.lead_id} created.")
        if self.object.assigned_salesperson:
            LeadAssignment.objects.create(
                lead=self.object, assigned_to=self.object.assigned_salesperson,
                assigned_by=self.request.user, method="manual",
            )
            notify(
                self.object.assigned_salesperson, f"New lead assigned: {self.object.lead_id}",
                url=self.object.get_absolute_url(), related_object=self.object,
            )
        return response

    def get_success_url(self):
        return reverse("crm:lead_detail", args=[self.object.pk])


class LeadUpdateView(LoginRequiredMixin, AutoLocalExportMixin, UpdateView):
    model = Lead
    form_class = LeadUpdateForm
    template_name = "crm/lead_form.html"

    def get_success_url(self):
        return reverse("crm:lead_detail", args=[self.object.pk])


@login_required
def lead_pipeline(request):
    statuses = LeadStatus.objects.filter(is_won=False, is_lost=False).order_by("sequence")
    qs = Lead.objects.select_related("customer", "status")
    if not request.user.has_role("Super Admin", "Management", "Sales Manager", "Admin Staff"):
        qs = qs.filter(assigned_salesperson=request.user)
    columns = [{"status": s, "leads": qs.filter(status=s)} for s in statuses]
    return render(request, "crm/lead_pipeline.html", {"columns": columns})


@login_required
@require_POST
def lead_assign(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    form = LeadAssignForm(request.POST)
    if form.is_valid():
        employee = form.cleaned_data["assigned_to"]
        lead.assigned_salesperson = employee
        assigned_status = LeadStatus.objects.filter(name__iexact="Assigned").first()
        if assigned_status:
            lead.status = assigned_status
        lead.save()
        LeadAssignment.objects.create(lead=lead, assigned_to=employee, assigned_by=request.user, method="manual")
        notify(employee, f"Lead assigned to you: {lead.lead_id}", url=lead.get_absolute_url(), related_object=lead)
        messages.success(request, f"Lead assigned to {employee}.")
    return redirect("crm:lead_detail", pk=pk)


@login_required
@require_POST
def followup_create(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    form = FollowUpForm(request.POST)
    if form.is_valid():
        followup = form.save(commit=False)
        followup.lead = lead
        followup.created_by = request.user
        followup.date = timezone.now().date()
        followup.save()
        messages.success(request, "Follow-up recorded.")
    else:
        messages.error(request, "Please correct the errors in the follow-up form.")
    return redirect("crm:lead_detail", pk=pk)


@login_required
def lead_mark_won(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    quotation = lead.quotations.order_by("-version").first() if hasattr(lead, "quotations") else None
    if not quotation:
        messages.error(request, "A quotation must exist before this lead can be marked as Won.")
        return redirect("crm:lead_detail", pk=pk)
    return redirect(f"{reverse('sales:order_create')}?lead={lead.pk}")


@login_required
def lead_mark_lost(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    if hasattr(lead, "lost_detail"):
        messages.info(request, "This lead is already marked as Lost.")
        return redirect("crm:lead_detail", pk=pk)

    if request.method == "POST":
        form = LostLeadForm(request.POST)
        if form.is_valid():
            detail = form.save(commit=False)
            detail.lead = lead
            detail.created_by = request.user
            detail.save()
            lost_status = LeadStatus.objects.filter(is_lost=True).first()
            if lost_status:
                lead.status = lost_status
                lead.save(update_fields=["status"])

            from apps.accounts.models import User
            from apps.core.notifications import notify_many

            reason = detail.reason.name if detail.reason_id else "No reason recorded"
            recipients = User.objects.filter(groups__name__in=["Sales Manager", "Management"], is_active=True).distinct()
            notify_many(
                recipients, f"Lead Lost: {lead.lead_id} — {reason}",
                url=lead.get_absolute_url(), related_object=lead,
            )

            messages.warning(request, f"Lead {lead.lead_id} marked as Lost.")
            return redirect("crm:lead_detail", pk=pk)
    else:
        form = LostLeadForm()
    return render(request, "crm/lead_lost_form.html", {"lead": lead, "form": form})
