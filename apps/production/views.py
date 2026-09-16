from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from apps.core.mixins import AutoLocalExportMixin, RoleRequiredMixin, require_role
from apps.core.models import QCChecklistItem
from apps.production.forms import ProductionSheetItemFormSet, ProductionTaskUpdateForm, QualityCheckForm
from apps.production.models import ProductionSheet, ProductionTask, QualityCheck
from apps.production import services


class ProductionSheetListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    section = "production"
    model = ProductionSheet
    template_name = "production/sheet_list.html"
    context_object_name = "sheets"
    paginate_by = 30

    def get_queryset(self):
        return ProductionSheet.objects.select_related("order").order_by("-created_at")


class ProductionSheetDetailView(LoginRequiredMixin, RoleRequiredMixin, AutoLocalExportMixin, DetailView):
    section = "production"
    model = ProductionSheet
    template_name = "production/sheet_detail.html"
    context_object_name = "sheet"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.accounts.models import User

        ctx["item_formset"] = ProductionSheetItemFormSet(instance=self.object)
        ctx["tasks"] = self.object.tasks.select_related("stage", "assigned_to")
        ctx["employees"] = User.objects.filter(is_active=True).order_by("first_name")
        ctx["can_approve_sheet"] = self.request.user.has_role("Production Manager", "Management", "Super Admin")
        return ctx


@login_required
@require_POST
def sheet_save_items(request, pk):
    sheet = get_object_or_404(ProductionSheet, pk=pk)
    formset = ProductionSheetItemFormSet(request.POST, instance=sheet)
    if formset.is_valid():
        formset.save()
        messages.success(request, "Production sheet items saved.")
    else:
        messages.error(request, "Please correct the errors below.")
    return redirect("production:sheet_detail", pk=pk)


@login_required
@require_POST
def sheet_submit(request, pk):
    sheet = get_object_or_404(ProductionSheet, pk=pk)
    services.submit_production_sheet(sheet, request.user)
    messages.success(request, "Production sheet submitted for approval.")
    return redirect("production:sheet_detail", pk=pk)


@require_role("Production Manager", "Management")
@require_POST
def sheet_approve(request, pk):
    sheet = get_object_or_404(ProductionSheet, pk=pk)
    services.approve_production_sheet(sheet, request.user)
    messages.success(request, "Production sheet approved. Production stage tasks created.")
    return redirect(f"{reverse('production:sheet_detail', args=[pk])}?autoexport=1")


@login_required
@require_POST
def task_update(request, pk):
    task = get_object_or_404(ProductionTask, pk=pk)
    previous_assignee_id = task.assigned_to_id
    form = ProductionTaskUpdateForm(request.POST, instance=task)
    if form.is_valid():
        task = form.save(commit=False)
        if task.status in ("started", "in_progress") and not task.start_time:
            task.start_time = timezone.now()
        if task.status == "completed" and not task.end_time:
            task.end_time = timezone.now()
        task.save()

        if task.assigned_to_id and task.assigned_to_id != previous_assignee_id:
            from apps.core.notifications import notify

            notify(
                task.assigned_to, f"You've been assigned: {task.stage.name} on {task.production_sheet.production_number}",
                url=task.production_sheet.get_absolute_url(), related_object=task.production_sheet,
            )

        services.maybe_complete_production(task.production_sheet)
        messages.success(request, f"{task.stage.name} updated to {task.get_status_display()}.")
    return redirect("production:sheet_detail", pk=task.production_sheet_id)


class QualityCheckListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    section = "production"
    model = QualityCheck
    template_name = "production/qc_list.html"
    context_object_name = "checks"

    def get_queryset(self):
        return QualityCheck.objects.select_related("production_sheet__order").order_by("status", "-created_at")


@login_required
def qc_detail(request, pk):
    qc = get_object_or_404(QualityCheck, pk=pk)
    checklist_items = QCChecklistItem.objects.filter(is_active=True)
    can_approve = request.user.has_role("Quality Control", "Production Manager", "Management", "Super Admin")

    if request.method == "POST":
        if not can_approve:
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("Only Quality Control can record the QC result.")
        form = QualityCheckForm(request.POST, instance=qc)
        if form.is_valid():
            for item in checklist_items:
                passed = request.POST.get(f"passed_{item.pk}") == "on"
                qc.results.update_or_create(checklist_item=item, defaults={"passed": passed})
            result_status = form.cleaned_data["status"]
            services.process_qc_result(qc, request.user, result_status, form.cleaned_data["remarks"])
            if result_status == "approved":
                from django.utils.html import format_html

                dispatch = qc.production_sheet.order.dispatch
                messages.success(
                    request,
                    format_html('Quality check approved. <a href="{}">View Dispatch</a>.', dispatch.get_absolute_url()),
                )
            else:
                messages.success(request, f"Quality check recorded: {qc.get_status_display()}.")
            return redirect("production:sheet_detail", pk=qc.production_sheet_id)
    else:
        form = QualityCheckForm(instance=qc)

    existing_results = {r.checklist_item_id: r.passed for r in qc.results.all()}
    return render(request, "production/qc_detail.html", {
        "qc": qc, "form": form, "checklist_items": checklist_items, "existing_results": existing_results,
        "can_approve": can_approve,
    })
