from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import DetailView, ListView

from apps.aftersales.forms import ServiceComplaintForm, ServiceComplaintUpdateForm
from apps.aftersales.models import ServiceComplaint, Warranty
from apps.core.mixins import AutoLocalExportMixin, RoleRequiredMixin
from apps.core.notifications import notify


class WarrantyListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    section = "aftersales"
    model = Warranty
    template_name = "aftersales/warranty_list.html"
    context_object_name = "warranties"
    paginate_by = 30

    def get_queryset(self):
        return Warranty.objects.select_related("order__customer").order_by("-created_at")


class WarrantyDetailView(LoginRequiredMixin, RoleRequiredMixin, AutoLocalExportMixin, DetailView):
    section = "aftersales"
    model = Warranty
    template_name = "aftersales/warranty_detail.html"
    context_object_name = "warranty"


class ComplaintListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    section = "aftersales"
    model = ServiceComplaint
    template_name = "aftersales/complaint_list.html"
    context_object_name = "complaints"
    paginate_by = 30

    def get_queryset(self):
        qs = ServiceComplaint.objects.select_related("customer", "assigned_technician").order_by("-complaint_date")
        if not self.request.user.has_role("Super Admin", "Management", "Admin Staff"):
            qs = qs.filter(assigned_technician=self.request.user)
        return qs


class ComplaintDetailView(LoginRequiredMixin, RoleRequiredMixin, AutoLocalExportMixin, DetailView):
    section = "aftersales"
    model = ServiceComplaint
    template_name = "aftersales/complaint_detail.html"
    context_object_name = "complaint"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = ServiceComplaintUpdateForm(instance=self.object)
        return ctx


@login_required
def complaint_create(request):
    customer_id = request.GET.get("customer")
    initial = {"customer": customer_id} if customer_id else {}
    if request.method == "POST":
        form = ServiceComplaintForm(request.POST)
        if form.is_valid():
            complaint = form.save()
            if complaint.assigned_technician:
                notify(
                    complaint.assigned_technician, f"New service complaint: {complaint.complaint_number}",
                    url=complaint.get_absolute_url(), related_object=complaint,
                )
            messages.success(request, f"Complaint {complaint.complaint_number} logged.")
            return redirect(f"{reverse('aftersales:complaint_detail', args=[complaint.pk])}?autoexport=1")
    else:
        form = ServiceComplaintForm(initial=initial)
    return render(request, "aftersales/complaint_form.html", {"form": form})


@login_required
def complaint_update(request, pk):
    complaint = get_object_or_404(ServiceComplaint, pk=pk)
    if request.method == "POST":
        form = ServiceComplaintUpdateForm(request.POST, instance=complaint)
        if form.is_valid():
            form.save()
            messages.success(request, "Complaint updated.")
            return redirect(f"{reverse('aftersales:complaint_detail', args=[pk])}?autoexport=1")
    return redirect("aftersales:complaint_detail", pk=pk)
