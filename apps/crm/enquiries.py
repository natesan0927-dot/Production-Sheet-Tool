"""Quick enquiries: a customer's call, passed by the Super Admin straight to a sales executive.

When a customer rings with a quick question, the Super Admin opens Quick enquiry
(a shortcut on the phone's home screen), types the number, the name if they have
it, and what they asked, and taps the sales executive who should call back.

That person gets a notification on their phone at once, marked urgent; a pop-up
the next time they open the app; and the newest one as a banner at the top of
every page, older ones pinned at the top of Notifications — until they press
"Addressed". It then stays at the top of their to-do, asking what became of it:
"Create as a lead" (the new-lead form, filled in from the enquiry) or "Junk it".
Either way the Super Admin is told, with the customer's name and number.
"""

import re

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
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
    customer_name = forms.CharField(label="Customer's name", max_length=150, required=False)
    remarks = forms.CharField(label="What was the enquiry?", max_length=1000, widget=forms.Textarea, required=False)
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

    def clean_customer_name(self):
        return " ".join(self.cleaned_data["customer_name"].split())

    def clean_remarks(self):
        return self.cleaned_data["remarks"].strip()


# ---------------------------------------------------------------- what happens to one
def _decide_title(enquiry):
    return f"Enquiry from {enquiry.who}: create a lead or junk it"


def mark_addressed(enquiry, user):
    """Called back. Off the banner and the pins; on the to-do, waiting to be made a lead or junked."""
    if not enquiry.is_open:
        return False
    enquiry.addressed_at = timezone.now()
    enquiry.save(update_fields=["addressed_at"])
    updates.clear(updates.enquiry(enquiry))
    if enquiry.task_id:
        Task.objects.filter(pk=enquiry.task_id).update(title=_decide_title(enquiry)[:200])
    return True


def settle(enquiry, user, outcome, lead=None):
    """Made a lead or junked: the to-do is done, and the Super Admin hears what became of it."""
    if enquiry.outcome:
        return False
    now = timezone.now()
    enquiry.addressed_at = enquiry.addressed_at or now
    enquiry.outcome, enquiry.outcome_at, enquiry.lead = outcome, now, lead
    enquiry.save(update_fields=["addressed_at", "outcome", "outcome_at", "lead"])
    updates.clear(updates.enquiry(enquiry))
    task = enquiry.task
    if task and not task.done:
        task.done, task.done_at = True, now
        task.save(update_fields=["done", "done_at"])
        updates.clear(updates.todo(task))
    if enquiry.created_by_id and enquiry.created_by_id != user.pk:
        what = "created a lead from" if outcome == Enquiry.Outcome.LEAD else "junked"
        updates.send(
            [enquiry.created_by],
            f"{user.display_name} {what} the enquiry — {enquiry.who}",
            lead=lead,
            topic=updates.todo_finished(task) if task else "",
            link=lead.get_absolute_url() if lead else reverse("crm:enquiry_detail", args=[enquiry.pk]),
        )
    return True


def complete_task(task, user):
    """A to-do marked done: whoever handed it out is told.

    An enquiry's to-do is not simply ticked off: the first tick is "Addressed",
    and after that it is finished by making it a lead or junking it.
    """
    if task.done:
        return False
    enquiry = Enquiry.objects.filter(task=task).first()
    if enquiry is not None:
        return mark_addressed(enquiry, user)
    task.done = True
    task.done_at = timezone.now()
    task.save(update_fields=["done", "done_at"])
    updates.clear(updates.todo(task))
    if task.assigned_by_id and task.assigned_by_id != user.pk:
        updates.send([task.assigned_by], f"{user.display_name} completed: {task.title}",
                     topic=updates.todo_finished(task), link=f"{updates.todo_link()}#assigned")
    return True


# ---------------------------------------------------------------- the pages
@login_required
def send(request):
    """The quick-enquiry screen: a number, a name if known, what they asked, and who calls back."""
    if not request.user.is_super_admin:
        # The home-screen shortcut is on everyone's phone; only the Super Admin sends.
        messages.info(request, "Quick enquiries are sent by the Super Admin. Yours arrive here and on your to-do.")
        return redirect("crm:dashboard")
    form = EnquiryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        person = data["assigned_to"]
        enquiry = Enquiry(phone=data["phone"], customer_name=data["customer_name"], remarks=data["remarks"],
                          assigned_to=person, created_by=request.user)
        enquiry.task = Task.objects.create(
            title=f"Urgent enquiry — call {enquiry.who}"[:200],
            details=data["remarks"],
            assigned_to=person,
            assigned_by=request.user,
            due_date=timezone.localdate(),
        )
        enquiry.save()
        updates.send(
            [person],
            f"URGENT enquiry from {request.user.display_name}: call {enquiry.who}" + (f" — {enquiry.remarks}" if enquiry.remarks else ""),
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
            "recent": Enquiry.objects.select_related("assigned_to", "lead")[:LATEST],
        },
    )


@login_required
def detail(request, pk):
    """One enquiry: who to call and why, and what to do with it."""
    enquiry = get_object_or_404(Enquiry.objects.select_related("assigned_to", "created_by", "lead"), pk=pk)
    if enquiry.assigned_to_id != request.user.pk and not request.user.is_super_admin:
        return redirect("crm:dashboard")
    if enquiry.assigned_to_id == request.user.pk and enquiry.popped_at is None:
        # Seen here, so it need not pop up as well.
        Enquiry.objects.filter(pk=pk).update(popped_at=timezone.now())
    return render(request, "crm/enquiry_detail.html", {"enquiry": enquiry})


@login_required
@require_POST
def addressed(request, pk):
    """Called back — and then, straight away, the question of what became of it.

    The page asks "Create as a lead, or junk it?" there and then. Only if that
    is put off does it wait on the to-do.
    """
    enquiry = get_object_or_404(Enquiry, pk=pk, assigned_to=request.user)
    mark_addressed(enquiry, request.user)
    if "application/json" in request.headers.get("Accept", ""):
        return JsonResponse({
            "ok": True,
            "deciding": enquiry.deciding,
            "who": enquiry.who,
            "lead_url": f"{reverse('crm:lead_create')}?enquiry={enquiry.pk}",
            "junk_url": reverse("crm:enquiry_junk", args=[enquiry.pk]),
        })
    # Without the page's script: the enquiry's own page, which asks the same.
    return redirect("crm:enquiry_detail", pk=enquiry.pk)


@login_required
@require_POST
def junk(request, pk):
    enquiry = get_object_or_404(Enquiry, pk=pk, assigned_to=request.user)
    if settle(enquiry, request.user, Enquiry.Outcome.JUNK):
        messages.success(request, f"The enquiry from {enquiry.who} is junked.")
    return safe_next(request, reverse("crm:todo_list"))


def for_new_lead(request):
    """The enquiry a new lead is being made from, if it is this person's and still waiting for that."""
    pk = request.POST.get("enquiry") or request.GET.get("enquiry")
    if not (pk and str(pk).isdigit()):
        return None
    return Enquiry.objects.filter(pk=pk, assigned_to=request.user, outcome="").first()


def context(request):
    """For the person they are assigned to: the newest waiting enquiry for the banner, and a new one to pop up.

    Only the newest is shown as the alert; older ones wait pinned at the top of
    Notifications. A new one pops up once, the next time they open a page.
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
    return {"open_enquiries": waiting, "newest_enquiry": waiting[0], "enquiry_popup": fresh[:1]}
