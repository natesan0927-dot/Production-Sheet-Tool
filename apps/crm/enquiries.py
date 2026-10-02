"""Quick enquiries: a customer's call, passed by the Super Admin straight to a sales executive.

When a customer rings with a quick question, the Super Admin opens Quick enquiry
(a shortcut on the phone's home screen), types the number and what they asked,
and taps the sales executive who should call back. That person gets:

- a notification on their phone straight away, marked urgent;
- a pop-up the next time they open the app, with an "Addressed" button;
- a to-do, and a banner at the top of every page, until they mark it addressed.

Ticking the to-do done and pressing "Addressed" are the same thing, and the
Super Admin is told either way.
"""

import re

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import Role, User

from . import updates
from .models import Enquiry, Task
from .views import safe_next

LATEST = 20  # enquiries listed under the form


def _salespeople():
    return User.objects.filter(role=Role.SALESPERSON, is_active=True).order_by("first_name", "username")


class EnquiryForm(forms.Form):
    phone = forms.CharField(label="Customer's number", max_length=20)
    remarks = forms.CharField(label="What was the enquiry?", max_length=1000, widget=forms.Textarea)
    assigned_to = forms.ModelChoiceField(queryset=User.objects.none(), label="Assign to",
                                         error_messages={"required": "Tap the sales executive who should call back."})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = _salespeople()

    def clean_phone(self):
        typed = self.cleaned_data["phone"].strip()
        digits = re.sub(r"\D", "", typed)
        if not 6 <= len(digits) <= 15 or re.search(r"[^\d\s+\-()]", typed):
            raise forms.ValidationError("Enter the customer's phone number.")
        return " ".join(typed.split())

    def clean_remarks(self):
        return self.cleaned_data["remarks"].strip()


def complete_task(task, user):
    """A to-do marked done: whoever handed it out is told. If it was an enquiry, that is addressed too."""
    if task.done:
        return False
    now = timezone.now()
    task.done = True
    task.done_at = now
    task.save(update_fields=["done", "done_at"])
    updates.clear(updates.todo(task))

    enquiry = Enquiry.objects.filter(task=task, addressed_at__isnull=True).first()
    if enquiry is not None:
        enquiry.addressed_at = now
        enquiry.save(update_fields=["addressed_at"])
        updates.clear(updates.enquiry(enquiry))
    if task.assigned_by_id and task.assigned_by_id != user.pk:
        message = (
            f"{user.display_name} addressed the enquiry from {enquiry.phone}" if enquiry
            else f"{user.display_name} completed: {task.title}"
        )
        updates.send([task.assigned_by], message, topic=updates.todo_finished(task), link=f"{updates.todo_link()}#assigned")
    return True


@login_required
def send(request):
    """The quick-enquiry screen: a number, what they asked, and who calls back."""
    if not request.user.is_super_admin:
        # The home-screen shortcut is on everyone's phone; only the Super Admin sends.
        messages.info(request, "Quick enquiries are sent by the Super Admin. Yours arrive here and on your to-do.")
        return redirect("crm:dashboard")
    form = EnquiryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        person = data["assigned_to"]
        task = Task.objects.create(
            title=f"Urgent enquiry — call {data['phone']}",
            details=data["remarks"],
            assigned_to=person,
            assigned_by=request.user,
            due_date=timezone.localdate(),
        )
        enquiry = Enquiry.objects.create(phone=data["phone"], remarks=data["remarks"], assigned_to=person,
                                         created_by=request.user, task=task)
        updates.send(
            [person],
            f"URGENT enquiry from {request.user.display_name}: call {enquiry.phone} — {enquiry.remarks}",
            topic=updates.enquiry(enquiry),
            link=reverse("crm:enquiry_detail", args=[enquiry.pk]),
        )
        messages.success(request, f"Sent to {person.display_name}. They have been notified on their phone.")
        return redirect("crm:enquiry")
    return render(
        request,
        "crm/enquiry.html",
        {
            "form": form,
            "salespeople": _salespeople(),
            "picked": str(form["assigned_to"].value() or ""),
            "recent": Enquiry.objects.select_related("assigned_to")[:LATEST],
        },
    )


@login_required
def detail(request, pk):
    """One enquiry: who to call and why, and the button to say it is dealt with."""
    enquiry = get_object_or_404(Enquiry.objects.select_related("assigned_to", "created_by"), pk=pk)
    if enquiry.assigned_to_id != request.user.pk and not request.user.is_super_admin:
        return redirect("crm:dashboard")
    if enquiry.assigned_to_id == request.user.pk and enquiry.popped_at is None:
        # Seen here, so it need not pop up as well.
        Enquiry.objects.filter(pk=pk).update(popped_at=timezone.now())
    return render(request, "crm/enquiry_detail.html", {"enquiry": enquiry})


@login_required
@require_POST
def addressed(request, pk):
    enquiry = get_object_or_404(Enquiry, pk=pk, assigned_to=request.user)
    if enquiry.is_open:
        if enquiry.task_id:
            complete_task(enquiry.task, request.user)
        else:
            enquiry.addressed_at = timezone.now()
            enquiry.save(update_fields=["addressed_at"])
            updates.clear(updates.enquiry(enquiry))
        messages.success(request, f"Enquiry from {enquiry.phone} marked addressed.")
    return safe_next(request, reverse("crm:dashboard"))


def context(request):
    """For the person they are assigned to: open enquiries for the banner, and new ones to pop up.

    A new one pops up once, the next time they open a page; closing the pop-up
    leaves it on the to-do and the banner until it is addressed.
    """
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated) or request.path in ("/sw.js", "/offline/"):
        return {}
    waiting = list(Enquiry.objects.filter(assigned_to=user, addressed_at__isnull=True).select_related("created_by"))
    if not waiting:
        return {}
    fresh = [e for e in waiting if e.popped_at is None]
    if fresh and not request.path.startswith("/enquiry/"):
        Enquiry.objects.filter(pk__in=[e.pk for e in fresh]).update(popped_at=timezone.now())
    else:
        fresh = []
    return {"open_enquiries": waiting, "enquiry_popup": fresh}
