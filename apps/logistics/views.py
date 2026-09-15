from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from apps.core.mixins import AutoLocalExportMixin, RoleRequiredMixin
from apps.logistics import services
from apps.logistics.forms import DispatchForm, HandoverForm, InstallationForm, SiteNotReadyForm
from apps.logistics.models import Dispatch, Installation


class DispatchListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    section = "dispatch"
    model = Dispatch
    template_name = "logistics/dispatch_list.html"
    context_object_name = "dispatches"
    paginate_by = 30

    def get_queryset(self):
        return Dispatch.objects.select_related("order__customer").order_by("-created_at")


class DispatchDetailView(LoginRequiredMixin, RoleRequiredMixin, AutoLocalExportMixin, DetailView):
    section = "dispatch"
    model = Dispatch
    template_name = "logistics/dispatch_detail.html"
    context_object_name = "dispatch"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = DispatchForm(instance=self.object)
        return ctx


@login_required
@require_POST
def dispatch_update(request, pk):
    dispatch = get_object_or_404(Dispatch, pk=pk)
    form = DispatchForm(request.POST, instance=dispatch)
    if form.is_valid():
        form.save()
        messages.success(request, "Dispatch details saved.")
    return redirect("logistics:dispatch_detail", pk=pk)


@login_required
@require_POST
def dispatch_mark_dispatched(request, pk):
    dispatch = get_object_or_404(Dispatch, pk=pk)
    services.mark_dispatched(dispatch, request.user)
    messages.success(request, "Order marked as dispatched. Installation task created.")
    return redirect(f"{reverse('logistics:dispatch_detail', args=[pk])}?autoexport=1")


class InstallationListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    section = "installation"
    model = Installation
    template_name = "logistics/installation_list.html"
    context_object_name = "installations"
    paginate_by = 30

    def get_queryset(self):
        qs = Installation.objects.select_related("order__customer").order_by("-created_at")
        if not self.request.user.has_role("Super Admin", "Management", "Admin Staff"):
            qs = qs.filter(installation_team=self.request.user) | qs.filter(team_leader=self.request.user)
        return qs.distinct()


class InstallationDetailView(LoginRequiredMixin, RoleRequiredMixin, AutoLocalExportMixin, DetailView):
    section = "installation"
    model = Installation
    template_name = "logistics/installation_detail.html"
    context_object_name = "installation"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = InstallationForm(instance=self.object)
        ctx["site_not_ready_form"] = SiteNotReadyForm()
        ctx["handover_form"] = HandoverForm()
        return ctx


@login_required
@require_POST
def installation_update(request, pk):
    installation = get_object_or_404(Installation, pk=pk)
    form = InstallationForm(request.POST, instance=installation)
    if form.is_valid():
        installation = form.save(commit=False)
        if installation.status == "pending" and installation.scheduled_date:
            installation.status = "scheduled"
        installation.save()
        form.save_m2m()
        messages.success(request, "Installation schedule saved.")
    return redirect("logistics:installation_detail", pk=pk)


@login_required
@require_POST
def installation_site_not_ready(request, pk):
    installation = get_object_or_404(Installation, pk=pk)
    form = SiteNotReadyForm(request.POST)
    if form.is_valid():
        log = form.save(commit=False)
        log.installation = installation
        log.logged_by = request.user
        log.save()
        installation.status = "site_not_ready"
        installation.save(update_fields=["status"])

        if installation.order.salesperson:
            from apps.core.notifications import notify

            notify(
                installation.order.salesperson,
                f"Site not ready for installation: {installation.installation_id} ({log.get_reason_display()})",
                url=installation.get_absolute_url(), related_object=installation,
            )

        messages.warning(request, "Logged as Site Not Ready and flagged for rescheduling.")
    return redirect("logistics:installation_detail", pk=pk)


@login_required
@require_POST
def installation_complete(request, pk):
    installation = get_object_or_404(Installation, pk=pk)
    services.mark_installation_completed(installation, request.user)
    messages.success(request, "Installation marked as completed.")
    return redirect("logistics:installation_detail", pk=pk)


@login_required
@require_POST
def installation_handover(request, pk):
    installation = get_object_or_404(Installation, pk=pk)
    form = HandoverForm(request.POST, request.FILES)
    if form.is_valid():
        services.generate_handover(
            installation, request.user,
            customer_confirmation=form.cleaned_data["customer_confirmation"],
            remarks=form.cleaned_data["remarks"],
            signature_file=form.cleaned_data.get("customer_signature"),
        )
        messages.success(request, "Handover certificate generated and warranty activated.")
    return redirect(f"{reverse('logistics:installation_detail', args=[pk])}?autoexport=1")
