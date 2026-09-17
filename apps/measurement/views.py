from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from apps.core.mixins import AutoLocalExportMixin, RoleRequiredMixin, require_role
from apps.core.models import Attachment
from apps.core.notifications import notify
from apps.crm.models import Lead
from apps.measurement.forms import (
    FinalMeasurementItemFormSet, FinalMeasurementRequestForm, MeasurementItemFormSet, MeasurementRequestForm,
    SiteReadyUncertainForm,
)
from apps.measurement.models import FinalMeasurementRequest, MeasurementRequest
from apps.sales.models import Order


# ---------------------------------------------------------------------------
# Site measurement (pre-quotation)
# ---------------------------------------------------------------------------
class MeasurementRequestListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    section = "measurement"
    model = MeasurementRequest
    template_name = "measurement/request_list.html"
    context_object_name = "requests"
    paginate_by = 30

    def get_queryset(self):
        qs = MeasurementRequest.objects.select_related("customer", "assigned_to").order_by("-requested_date")
        if not self.request.user.has_role("Super Admin", "Management", "Sales Manager", "Admin Staff"):
            qs = qs.filter(assigned_to=self.request.user)
        return qs


class MeasurementRequestDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    section = "measurement"
    model = MeasurementRequest
    template_name = "measurement/request_detail.html"
    context_object_name = "measurement"

    def get_context_data(self, **kwargs):
        from django.contrib.contenttypes.models import ContentType

        ctx = super().get_context_data(**kwargs)
        ctx["item_formset"] = MeasurementItemFormSet(instance=self.object)
        ctx["attachments"] = Attachment.objects.filter(
            content_type=ContentType.objects.get_for_model(MeasurementRequest), object_id=self.object.pk
        )
        return ctx


@login_required
def request_create(request):
    lead_id = request.GET.get("lead")
    lead = get_object_or_404(Lead, pk=lead_id)
    existing = lead.measurement_requests.exclude(status="cancelled").first()
    if existing:
        messages.info(request, f"A measurement is already requested for this lead ({existing.measurement_id}).")
        return redirect("measurement:request_detail", pk=existing.pk)
    if request.method == "POST":
        form = MeasurementRequestForm(request.POST)
        if form.is_valid():
            measurement = form.save(commit=False)
            measurement.lead = lead
            measurement.customer = lead.customer
            measurement.requested_by = request.user
            if measurement.assigned_to:
                measurement.status = "assigned"
            measurement.save()

            from apps.core.models import LeadStatus

            pending_status = LeadStatus.objects.filter(name__icontains="Measurement Pending").first()
            if pending_status:
                lead.status = pending_status
                lead.save(update_fields=["status"])

            if measurement.assigned_to:
                notify(
                    measurement.assigned_to, f"New measurement job: {measurement.measurement_id}",
                    url=measurement.get_absolute_url(), related_object=measurement,
                )
            messages.success(request, f"Measurement request {measurement.measurement_id} created.")
            return redirect("measurement:request_detail", pk=measurement.pk)
    else:
        form = MeasurementRequestForm(initial={"site_address": lead.customer.project_address or lead.customer.address, "contact_person": lead.customer.contact_person})
    return render(request, "measurement/request_form.html", {"form": form, "lead": lead})


@login_required
@require_POST
def request_save_items(request, pk):
    measurement = get_object_or_404(MeasurementRequest, pk=pk)
    formset = MeasurementItemFormSet(request.POST, instance=measurement)
    if formset.is_valid():
        formset.save()
        messages.success(request, "Measurement details saved.")
    else:
        messages.error(request, "Please correct the errors in the measurement items.")
    return redirect("measurement:request_detail", pk=pk)


@login_required
@require_POST
def request_upload_attachment(request, pk):
    from django.contrib.contenttypes.models import ContentType

    measurement = get_object_or_404(MeasurementRequest, pk=pk)
    files = request.FILES.getlist("files")
    category = request.POST.get("category", "site_photo")
    for f in files:
        Attachment.objects.create(
            content_type=ContentType.objects.get_for_model(MeasurementRequest), object_id=measurement.pk,
            category=category, file=f, uploaded_by=request.user,
        )
    messages.success(request, f"{len(files)} file(s) uploaded.")
    return redirect("measurement:request_detail", pk=pk)


@login_required
@require_POST
def request_complete(request, pk):
    measurement = get_object_or_404(MeasurementRequest, pk=pk)
    measurement.status = "completed"
    measurement.completed_at = timezone.now()
    measurement.save(update_fields=["status", "completed_at"])

    from apps.core.models import LeadStatus

    lead = measurement.lead
    done_status = LeadStatus.objects.filter(name__icontains="Measurement Completed").first()
    if done_status:
        lead.status = done_status
        lead.save(update_fields=["status"])

    if lead.assigned_salesperson:
        notify(
            lead.assigned_salesperson, f"Measurement completed for {lead.lead_id}",
            url=lead.get_absolute_url(), related_object=lead,
        )
    messages.success(request, "Measurement marked as completed. Salesperson notified.")
    return redirect("measurement:request_detail", pk=pk)


# ---------------------------------------------------------------------------
# Final measurement (post order)
# ---------------------------------------------------------------------------
class FinalMeasurementListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    section = "measurement"
    model = FinalMeasurementRequest
    template_name = "measurement/final_list.html"
    context_object_name = "requests"
    paginate_by = 30

    def get_queryset(self):
        qs = FinalMeasurementRequest.objects.select_related("order").order_by("-id")
        if not self.request.user.has_role("Super Admin", "Management", "Sales Manager", "Admin Staff"):
            qs = qs.filter(assigned_to=self.request.user)
        return qs


class FinalMeasurementDetailView(LoginRequiredMixin, RoleRequiredMixin, DetailView):
    section = "measurement"
    model = FinalMeasurementRequest
    template_name = "measurement/final_detail.html"
    context_object_name = "final_measurement"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["item_formset"] = FinalMeasurementItemFormSet(instance=self.object)
        ctx["can_approve"] = self.request.user.has_role("Admin Staff", "Production Manager", "Management", "Super Admin")
        return ctx


@login_required
def final_create(request):
    order_id = request.GET.get("order")
    order = get_object_or_404(Order, pk=order_id)
    if request.method == "POST":
        form = FinalMeasurementRequestForm(request.POST)
        if form.is_valid():
            fm = form.save(commit=False)
            fm.order = order
            if fm.assigned_to:
                fm.status = "assigned"
            fm.save()
            order.status = "final_measurement"
            order.save(update_fields=["status"])
            if fm.assigned_to:
                notify(fm.assigned_to, f"Final measurement assigned: {fm.final_measurement_id}", url=fm.get_absolute_url(), related_object=fm)
            messages.success(request, f"Final measurement {fm.final_measurement_id} created.")
            return redirect("measurement:final_detail", pk=fm.pk)
    else:
        form = FinalMeasurementRequestForm()
    return render(request, "measurement/final_form.html", {"form": form, "order": order})


@login_required
@require_POST
def final_site_not_ready(request, pk):
    fm = get_object_or_404(FinalMeasurementRequest, pk=pk)
    form = SiteReadyUncertainForm(request.POST)
    if form.is_valid():
        fm.site_ready_uncertain = True
        fm.site_ready_expected_date = form.cleaned_data["site_ready_expected_date"]
        fm.save(update_fields=["site_ready_uncertain", "site_ready_expected_date"])
        if fm.order.salesperson:
            notify(
                fm.order.salesperson,
                f"Site not ready for final measurement: {fm.final_measurement_id} (expected {fm.site_ready_expected_date})",
                url=fm.get_absolute_url(), related_object=fm,
            )
        messages.warning(request, "Marked as site-not-ready. This will keep showing as a reminder until it's cleared.")
    return redirect("measurement:final_detail", pk=pk)


@login_required
@require_POST
def final_site_ready(request, pk):
    fm = get_object_or_404(FinalMeasurementRequest, pk=pk)
    fm.site_ready_uncertain = False
    fm.site_ready_expected_date = None
    fm.save(update_fields=["site_ready_uncertain", "site_ready_expected_date"])
    messages.success(request, "Site marked ready.")
    return redirect("measurement:final_detail", pk=pk)


@login_required
@require_POST
def final_save_items(request, pk):
    fm = get_object_or_404(FinalMeasurementRequest, pk=pk)
    formset = FinalMeasurementItemFormSet(request.POST, instance=fm)
    if formset.is_valid():
        formset.save()
        fm.status = "completed"
        fm.completed_at = timezone.now()
        fm.save(update_fields=["status", "completed_at"])
        messages.success(request, "Final measurement details saved.")
    else:
        messages.error(request, "Please correct the errors below.")
    return redirect("measurement:final_detail", pk=pk)


@require_role("Admin Staff", "Production Manager", "Management")
@require_POST
def final_approve(request, pk):
    fm = get_object_or_404(FinalMeasurementRequest, pk=pk)
    fm.status = "approved"
    fm.approved_by = request.user
    fm.approved_at = timezone.now()
    fm.save(update_fields=["status", "approved_by", "approved_at"])

    from django.utils.html import format_html

    from apps.production.services import create_production_sheet_request

    sheet = create_production_sheet_request(fm.order, request.user)

    messages.success(
        request,
        format_html(
            'Final measurement approved. <a href="{}">View Production Sheet</a>.', sheet.get_absolute_url()
        ),
    )
    return redirect("measurement:final_detail", pk=pk)
