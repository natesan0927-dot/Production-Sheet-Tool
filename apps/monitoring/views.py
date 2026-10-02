"""Monitoring's pages.

The Super Admin: Employees, Attendance, Salary (advances), Reports, Site Visits.
A sales executive: Today's Work (site stops) and their own Site Visits. Nobody
else can open Monitoring.
"""

import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from apps.accounts.models import Role, User

from . import months, places, reports
from .forms import MonitoringLoginForm, WorkerForm
from .models import ZERO, Advance, Attendance, DayAdvance, ReopenedMonth, SiteStop, Worker, WorkDay

MOST_OVERTIME = Decimal("24")
MOST_ADVANCE = Decimal("1000000")


def _only(*roles):
    def decorate(view):
        @wraps(view)
        @login_required(login_url="monitoring:login")
        def wrapper(request, *args, **kwargs):
            if request.user.role not in roles:
                return HttpResponseForbidden("This part of Monitoring is not open to you.")
            return view(request, *args, **kwargs)

        return wrapper

    return decorate


admin_only = _only(Role.SUPER_ADMIN)
sales_only = _only(Role.SALESPERSON)
members = _only(Role.SUPER_ADMIN, Role.SALESPERSON)


class MonitoringLoginView(auth_views.LoginView):
    """Monitoring's own sign-in, from the button at the foot of the main one."""

    template_name = "monitoring/login.html"
    authentication_form = MonitoringLoginForm
    redirect_authenticated_user = False

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.role in (Role.SUPER_ADMIN, Role.SALESPERSON):
            return redirect("monitoring:home")
        return super().dispatch(request, *args, **kwargs)

    def get_default_redirect_url(self):
        return reverse("monitoring:home")


@members
def home(request):
    if request.user.is_super_admin:
        return redirect("monitoring:attendance")
    return redirect("monitoring:work")


# ---------------------------------------------------------------- employees
@admin_only
def employees(request):
    query = request.GET.get("q", "").strip()
    current = Worker.objects.filter(is_active=True)
    if query:
        current = current.filter(Q(name__icontains=query) | Q(designation__icontains=query) | Q(phone__icontains=query))
    return render(
        request,
        "monitoring/employees.html",
        {"workers": current, "removed": Worker.objects.filter(is_active=False), "q": query},
    )


@admin_only
def employee_add(request):
    form = WorkerForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        worker = form.save()
        messages.success(request, f"{worker.name} added.")
        return redirect("monitoring:employee", pk=worker.pk)
    return render(request, "monitoring/employee_form.html", {"form": form, "adding": True})


@admin_only
def employee_edit(request, pk):
    worker = get_object_or_404(Worker, pk=pk)
    form = WorkerForm(request.POST or None, instance=worker)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{worker.name}'s details saved.")
        return redirect("monitoring:employee", pk=worker.pk)
    return render(request, "monitoring/employee_form.html", {"form": form, "worker": worker})


@admin_only
@require_POST
def employee_remove(request, pk):
    """Taken off the roll. Their past attendance and advances stay, so old reports still add up."""
    worker = get_object_or_404(Worker, pk=pk, is_active=True)
    worker.is_active = False
    worker.left_on = timezone.localdate()
    worker.save(update_fields=["is_active", "left_on", "updated_at"])
    messages.success(request, f"{worker.name} removed. Their past records are kept; restore them from the list if needed.")
    return redirect("monitoring:employees")


@admin_only
@require_POST
def employee_restore(request, pk):
    worker = get_object_or_404(Worker, pk=pk, is_active=False)
    worker.is_active = True
    worker.left_on = None
    worker.save(update_fields=["is_active", "left_on", "updated_at"])
    messages.success(request, f"{worker.name} is back on the roll.")
    return redirect("monitoring:employee", pk=worker.pk)


@admin_only
def employee(request, pk):
    """Their details, the month's attendance on a calendar, and their advances."""
    worker = get_object_or_404(Worker, pk=pk)
    month = months.parse(request.GET.get("month"), months.this_month())
    if month > months.this_month():
        month = months.this_month()
    found = months.figures(worker, month)
    # The report for the month on screen once it has closed; otherwise the latest one ready.
    report_month = month if months.is_closed(month) else months.last_closed()
    if not months.covers(worker, report_month):
        report_month = None
    return render(
        request,
        "monitoring/employee.html",
        {
            "worker": worker,
            "month": month,
            "figures": found,
            "weeks": months.calendar_weeks(month, found.days, found.advances_by_day),
            "today": timezone.localdate(),
            "open": not months.is_closed(month),
            "previous_month": months.previous_month(month),
            "next_month": months.next_month(month) if month < months.this_month() else None,
            "report_month": report_month,
            "report_table": months.advance_table(worker, report_month) if report_month else None,
        },
    )


def _hours(text):
    """Overtime hours as typed, or None if they are not a sensible number."""
    text = (text or "").strip()
    if not text:
        return ZERO
    try:
        hours = Decimal(text).quantize(Decimal("0.1"))
    except InvalidOperation:
        return None
    return hours if ZERO <= hours <= MOST_OVERTIME else None


def _rupees(text):
    """An amount of money as typed, or None if it is not one."""
    text = (text or "").replace(",", "").replace("₹", "").strip()
    if not text:
        return ZERO
    try:
        amount = Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    return amount if ZERO <= amount <= MOST_ADVANCE else None


def _set_advance(worker, day, amount, user):
    """The advance given on a day: saved, changed, or taken off when it is nothing."""
    if amount:
        DayAdvance.objects.update_or_create(worker=worker, date=day, defaults={"amount": amount, "given_by": user})
    else:
        DayAdvance.objects.filter(worker=worker, date=day).delete()


@admin_only
@require_POST
def employee_day(request, pk):
    """One day from the calendar: its overtime and the advance given that day."""
    worker = get_object_or_404(Worker, pk=pk)
    day = parse_date(request.POST.get("date", "") or "")
    back = f"{reverse('monitoring:employee', args=[pk])}?month={day:%Y-%m}" if day else reverse("monitoring:employee", args=[pk])
    hours = _hours(request.POST.get("hours"))
    amount = _rupees(request.POST.get("advance"))
    if day is None or day > timezone.localdate():
        messages.error(request, "Only today or a day gone by can be changed.")
        return redirect(back)
    if months.is_closed(months.first_of(day)):
        messages.error(request, f"{day:%B %Y} is closed. Reopen it under Reports to correct it.")
        return redirect(back)
    if hours is None:
        messages.error(request, f"Enter the overtime as hours, from 0 to {MOST_OVERTIME:g}.")
        return redirect(back)
    if amount is None:
        messages.error(request, "Enter the advance as an amount in rupees.")
        return redirect(back)
    record = Attendance.objects.filter(worker=worker, date=day).first()
    if record and record.status == Attendance.Status.ABSENT and hours:
        messages.error(request, f"{worker.name} is marked absent on {day:%d %b}. Mark them present first.")
        return redirect(back)
    said = []
    if record:
        if record.overtime_hours != hours:
            record.overtime_hours = hours
            record.marked_by = request.user
            record.save(update_fields=["overtime_hours", "marked_by", "updated_at"])
            said.append(_overtime_said(hours))
    elif hours:
        # Overtime means they came in.
        Attendance.objects.create(worker=worker, date=day, status=Attendance.Status.PRESENT,
                                  overtime_hours=hours, marked_by=request.user)
        said.append(_overtime_said(hours) + ", marked present")
    before = DayAdvance.objects.filter(worker=worker, date=day).values_list("amount", flat=True).first() or ZERO
    if before != amount:
        _set_advance(worker, day, amount, request.user)
        said.append(f"advance ₹{amount:,.2f}" if amount else "advance cleared")
    messages.success(request, f"{worker.name}, {day:%d %b}: " + ("; ".join(said) if said else "nothing changed") + ".")
    return redirect(back)


def _overtime_said(hours):
    if not hours:
        return "overtime cleared"
    return f"{hours:g} hour{'s' if hours != 1 else ''} of overtime"


# ---------------------------------------------------------------- attendance
def _attendance_day(request):
    today = timezone.localdate()
    day = parse_date(request.GET.get("date", "") or request.POST.get("date", "") or "") or today
    return min(day, today)


@admin_only
def attendance(request):
    day = _attendance_day(request)
    month = months.first_of(day)
    closed = months.is_closed(month)
    records = {a.worker_id: a for a in Attendance.objects.filter(date=day)}
    advances = {a.worker_id: a.amount for a in DayAdvance.objects.filter(date=day)}
    roll = [w for w in Worker.objects.all() if w.on_roll(day) or w.pk in records or w.pk in advances]

    if request.method == "POST" and not closed:
        if "holiday" in request.POST:
            return _mark_holiday(request, day, roll, records)
        problems, changes = [], []
        for worker in roll:
            status = request.POST.get(f"status_{worker.pk}", "")
            hours = _hours(request.POST.get(f"ot_{worker.pk}"))
            amount = _rupees(request.POST.get(f"adv_{worker.pk}"))
            if status and status not in Attendance.Status.values:
                problems.append(f"{worker.name}: choose present, absent or half day.")
            elif hours is None:
                problems.append(f"{worker.name}: overtime has to be hours, from 0 to {MOST_OVERTIME:g}.")
            elif amount is None:
                problems.append(f"{worker.name}: the advance has to be an amount in rupees.")
            elif status == Attendance.Status.ABSENT and hours:
                problems.append(f"{worker.name} is marked absent but has overtime. Mark them present, or clear the overtime.")
            else:
                changes.append((worker, status or (Attendance.Status.PRESENT if hours else ""), hours, amount))
        if problems:
            for problem in problems:
                messages.error(request, problem)
        else:
            with transaction.atomic():
                for worker, status, hours, amount in changes:
                    if status:
                        Attendance.objects.update_or_create(
                            worker=worker, date=day,
                            defaults={"status": status, "overtime_hours": hours, "marked_by": request.user},
                        )
                    else:
                        Attendance.objects.filter(worker=worker, date=day).delete()
                    if advances.get(worker.pk, ZERO) != amount:
                        _set_advance(worker, day, amount, request.user)
            marked = sum(1 for _, status, _, _ in changes if status)
            given = sum((amount for *_, amount in changes), ZERO)
            note = f" Advances given: ₹{given:,.2f}." if given else ""
            messages.success(request, f"Attendance for {day:%A, %d %b %Y} saved — {marked} of {len(roll)} marked.{note}")
            return redirect(f"{reverse('monitoring:attendance')}?date={day.isoformat()}")
        # Show what they chose, with the problems, rather than what was saved.
        records = {
            worker.pk: Attendance(worker=worker, date=day, status=request.POST.get(f"status_{worker.pk}", ""),
                                  overtime_hours=_hours(request.POST.get(f"ot_{worker.pk}")) or ZERO)
            for worker in roll
        }
        advances = {worker.pk: request.POST.get(f"adv_{worker.pk}", "") for worker in roll}
    elif request.method == "POST":
        messages.error(request, f"{month:%B %Y} is closed. Reopen it under Reports to correct it.")

    rows = [{"worker": worker, "record": records.get(worker.pk), "advance": advances.get(worker.pk)} for worker in roll]
    holiday = bool(roll) and all(r["record"] and r["record"].status == Attendance.Status.HOLIDAY for r in rows)
    return render(
        request,
        "monitoring/attendance.html",
        {
            "day": day,
            "today": timezone.localdate(),
            "rows": rows,
            "closed": closed,
            "holiday": holiday,
            "marked": sum(1 for r in rows if r["record"] and r["record"].status),
            "previous_day": day - timedelta(days=1),
            "next_day": day + timedelta(days=1) if day < timezone.localdate() else None,
        },
    )


def _mark_holiday(request, day, roll, records):
    """Everyone on the roll gets the day as a holiday. Overtime already entered stays."""
    with transaction.atomic():
        for worker in roll:
            record = records.get(worker.pk)
            if record:
                record.status = Attendance.Status.HOLIDAY
                record.marked_by = request.user
                record.save(update_fields=["status", "marked_by", "updated_at"])
            else:
                Attendance.objects.create(worker=worker, date=day, status=Attendance.Status.HOLIDAY, marked_by=request.user)
    messages.success(request, f"{day:%A, %d %b %Y} marked as a holiday for all {len(roll)} employees.")
    return redirect(f"{reverse('monitoring:attendance')}?date={day.isoformat()}")


# ---------------------------------------------------------------- reports
@admin_only
def report_list(request):
    month = months.parse(request.GET.get("month"), months.last_closed())
    ready = months.closed_months()
    if month not in ready and ready:
        month = ready[0]
    return render(
        request,
        "monitoring/reports.html",
        {
            "month": month,
            "ready": ready,
            "reopened": [r.month for r in ReopenedMonth.objects.order_by("-month")],
            "workers": [{"worker": worker, "table": months.advance_table(worker, month)}
                        for worker in months.workers_for(month)] if ready else [],
            "is_reopened": months.is_reopened(month),
            "this_month": months.this_month(),
            "next_report": months.next_month(months.this_month()),
        },
    )


def _closed_month_or_404(text):
    month = months.parse(text)
    if month is None or month >= months.this_month():
        raise Http404("That month's report is ready on the 1st of the next.")
    return month


@admin_only
def report_excel(request, month):
    month = _closed_month_or_404(month)
    return reports.month_workbook(month)


@admin_only
def report_pdf(request, pk, month):
    worker = get_object_or_404(Worker, pk=pk)
    return reports.employee_pdf(worker, _closed_month_or_404(month))


@admin_only
@require_POST
def report_deduction(request, pk, month):
    """The amount to deduct for the month, asked for as the employee's report is downloaded.

    Saved for the month, so the report, the Excel sheet and next month's previous
    advance all follow it. Then the report itself is downloaded.
    """
    worker = get_object_or_404(Worker, pk=pk)
    month = _closed_month_or_404(month)
    table = months.advance_table(worker, month)
    amount = _rupees(request.POST.get("deduction"))
    problem = ""
    if amount is None:
        problem = "Enter the amount to deduct, in rupees."
    elif amount > table.owed:
        problem = f"That is more than the ₹{table.owed:,.2f} of advance they owe."
    elif amount > worker.monthly_salary:
        problem = f"That is more than their monthly salary of ₹{worker.monthly_salary:,.2f}."
    pdf_url = reverse("monitoring:report_pdf", args=[worker.pk, f"{month:%Y-%m}"])
    wants_json = "application/json" in request.headers.get("Accept", "")
    if problem:
        if wants_json:
            return JsonResponse({"ok": False, "error": problem}, status=400)
        messages.error(request, problem)
        return redirect(f"{reverse('monitoring:employee', args=[worker.pk])}?month={month:%Y-%m}")
    Advance.objects.update_or_create(worker=worker, month=month, defaults={"deduction": amount, "updated_by": request.user})
    if wants_json:
        return JsonResponse({"ok": True, "pdf": pdf_url})
    return redirect(pdf_url)


@admin_only
@require_POST
def month_reopen(request, month):
    month = _closed_month_or_404(month)
    ReopenedMonth.objects.get_or_create(month=month, defaults={"reopened_by": request.user})
    messages.success(request, f"{month:%B %Y} is open for corrections. Close it again when you are done.")
    return redirect(f"{reverse('monitoring:reports')}?month={month:%Y-%m}")


@admin_only
@require_POST
def month_close(request, month):
    month = _closed_month_or_404(month)
    ReopenedMonth.objects.filter(month=month).delete()
    messages.success(request, f"{month:%B %Y} is closed again. Its report includes your corrections.")
    return redirect(f"{reverse('monitoring:reports')}?month={month:%Y-%m}")


# ---------------------------------------------------------------- a sales executive's day out
def _where(request, required=True):
    """The location sent from the phone, or an error to show."""
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    try:
        latitude = Decimal(str(data["latitude"])).quantize(Decimal("0.000001"))
        longitude = Decimal(str(data["longitude"])).quantize(Decimal("0.000001"))
        accuracy = data.get("accuracy")
        accuracy = max(0, min(int(float(accuracy)), 100000)) if accuracy is not None else None
    except (ValueError, KeyError, TypeError, InvalidOperation):
        if not required:
            return {"latitude": None, "longitude": None, "accuracy": None, "data": data}, ""
        return None, "The phone did not send a location. Allow location for this app and try again."
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None, "That location is not on the map."
    return {"latitude": latitude, "longitude": longitude, "accuracy": accuracy, "data": data}, ""


def _today(user):
    return WorkDay.objects.filter(user=user, date=timezone.localdate()).first()


@sales_only
def work(request):
    day = _today(request.user)
    return render(
        request,
        "monitoring/work.html",
        {"day": day, "stops": day.stops.order_by("recorded_at") if day else [], "today": timezone.localdate()},
    )


@sales_only
@require_POST
def work_start(request):
    where, problem = _where(request)
    if problem:
        return JsonResponse({"ok": False, "error": problem}, status=400)
    day, created = WorkDay.objects.get_or_create(
        user=request.user, date=timezone.localdate(),
        defaults={"latitude": where["latitude"], "longitude": where["longitude"], "accuracy": where["accuracy"]},
    )
    if created:
        places.fill_in(WorkDay, day.pk)
    return JsonResponse({"ok": True, "started": f"{timezone.localtime(day.started_at):%I:%M %p}", "new": created})


@sales_only
@require_POST
def work_stop(request):
    where, problem = _where(request)
    if problem:
        return JsonResponse({"ok": False, "error": problem}, status=400)
    remark = " ".join(str(where["data"].get("remark") or "").split())
    if not remark:
        return JsonResponse({"ok": False, "error": "Write the site's name, and what happened there."}, status=400)
    if len(remark) > 1000:
        return JsonResponse({"ok": False, "error": "Keep the remark under 1000 characters."}, status=400)
    day = _today(request.user)
    if day is None:
        return JsonResponse({"ok": False, "error": "Start today's work first."}, status=400)
    if day.completed_at:
        return JsonResponse({"ok": False, "error": "Today's work is marked complete. Resume the day to add a stop."}, status=400)
    stop = SiteStop.objects.create(user=request.user, workday=day, latitude=where["latitude"], longitude=where["longitude"],
                                   accuracy=where["accuracy"], remark=remark)
    places.fill_in(SiteStop, stop.pk)
    return JsonResponse({"ok": True, "count": day.stops.count(), "at": f"{timezone.localtime(stop.recorded_at):%I:%M %p}"})


@sales_only
@require_POST
def work_complete(request):
    """The day's work is done: when, and where — if the phone could tell."""
    where, problem = _where(request, required=False)
    if problem:
        return JsonResponse({"ok": False, "error": problem}, status=400)
    day = _today(request.user)
    if day is None:
        return JsonResponse({"ok": False, "error": "Start today's work first."}, status=400)
    if not day.completed_at:
        day.completed_at = timezone.now()
        day.end_latitude, day.end_longitude, day.end_accuracy = where["latitude"], where["longitude"], where["accuracy"]
        day.save(update_fields=["completed_at", "end_latitude", "end_longitude", "end_accuracy"])
        if day.end_latitude is not None:
            places.fill_in(WorkDay, day.pk, "end_latitude", "end_longitude", "end_place")
    return JsonResponse({"ok": True, "completed": f"{timezone.localtime(day.completed_at):%I:%M %p}"})


@sales_only
@require_POST
def work_resume(request):
    """Completed by mistake: the day carries on."""
    day = _today(request.user)
    if day and day.completed_at:
        day.completed_at = None
        day.end_latitude = day.end_longitude = day.end_accuracy = None
        day.end_place = ""
        day.save(update_fields=["completed_at", "end_latitude", "end_longitude", "end_accuracy", "end_place"])
        messages.success(request, "Today's work is open again.")
    return redirect("monitoring:work")


def _timeline(day):
    """The day in order: started, each site stop, completed."""
    if day is None:
        return []
    events = [{"kind": "start", "at": day.started_at, "latitude": day.latitude, "longitude": day.longitude,
               "accuracy": day.accuracy, "place": day.place, "title": "Started the day"}]
    for stop in day.stops.order_by("recorded_at"):
        events.append({"kind": "stop", "at": stop.recorded_at, "latitude": stop.latitude, "longitude": stop.longitude,
                       "accuracy": stop.accuracy, "place": stop.place, "title": stop.remark})
    if day.completed_at:
        events.append({"kind": "end", "at": day.completed_at, "latitude": day.end_latitude, "longitude": day.end_longitude,
                       "accuracy": day.end_accuracy, "place": day.end_place, "title": "Completed the day"})
    return events


@members
def status(request):
    """One sales executive's day, as a timeline. A sales executive sees their own."""
    today = timezone.localdate()
    date = min(parse_date(request.GET.get("date", "") or "") or today, today)
    people = list(User.objects.filter(role=Role.SALESPERSON, is_active=True).order_by("first_name", "username"))
    if request.user.is_super_admin:
        picked = request.GET.get("salesperson", "")
        person = next((p for p in people if str(p.pk) == picked), None)
        if person is None and people:
            # Whoever was out that day first, or else the first on the list.
            out = set(WorkDay.objects.filter(date=date).values_list("user_id", flat=True))
            person = next((p for p in people if p.pk in out), people[0])
    else:
        person = request.user
    day = WorkDay.objects.filter(user=person, date=date).first() if person else None
    events = _timeline(day)
    return render(
        request,
        "monitoring/status.html",
        {
            "events": events,
            "day": day,
            "people": people if request.user.is_super_admin else [],
            "person": person,
            "date": date,
            "today": today,
            "previous_date": date - timedelta(days=1),
            "next_date": date + timedelta(days=1) if date < today else None,
            "stops_count": sum(1 for event in events if event["kind"] == "stop"),
        },
    )
