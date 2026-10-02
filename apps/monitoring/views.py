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

from . import months, reports
from .forms import AdvanceForm, MonitoringLoginForm, WorkerForm
from .models import ZERO, Advance, Attendance, ReopenedMonth, SiteStop, Worker, WorkDay

MOST_OVERTIME = Decimal("24")


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
            "weeks": months.calendar_weeks(month, found.days),
            "today": timezone.localdate(),
            "open": not months.is_closed(month),
            "previous_month": months.previous_month(month),
            "next_month": months.next_month(month) if month < months.this_month() else None,
            "report_month": report_month,
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


@admin_only
@require_POST
def employee_overtime(request, pk):
    """Overtime for one day, from the calendar."""
    worker = get_object_or_404(Worker, pk=pk)
    day = parse_date(request.POST.get("date", "") or "")
    back = f"{reverse('monitoring:employee', args=[pk])}?month={day:%Y-%m}" if day else reverse("monitoring:employee", args=[pk])
    hours = _hours(request.POST.get("hours"))
    if day is None or day > timezone.localdate():
        messages.error(request, "Overtime can only be entered for today or a day gone by.")
    elif months.is_closed(months.first_of(day)):
        messages.error(request, f"{day:%B %Y} is closed. Reopen it under Reports to correct it.")
    elif hours is None:
        messages.error(request, f"Enter the overtime as hours, from 0 to {MOST_OVERTIME:g}.")
    else:
        record = Attendance.objects.filter(worker=worker, date=day).first()
        if record and record.status == Attendance.Status.ABSENT and hours:
            messages.error(request, f"{worker.name} is marked absent on {day:%d %b}. Mark them present first.")
        elif record:
            record.overtime_hours = hours
            record.marked_by = request.user
            record.save(update_fields=["overtime_hours", "marked_by", "updated_at"])
            messages.success(request, _overtime_said(worker, day, hours))
        elif hours:
            # Overtime means they came in.
            Attendance.objects.create(worker=worker, date=day, status=Attendance.Status.PRESENT,
                                      overtime_hours=hours, marked_by=request.user)
            messages.success(request, _overtime_said(worker, day, hours) + " They are marked present.")
    return redirect(back)


def _overtime_said(worker, day, hours):
    if not hours:
        return f"Overtime on {day:%d %b} cleared for {worker.name}."
    return f"{hours:g} hour{'s' if hours != 1 else ''} of overtime on {day:%d %b} saved for {worker.name}."


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
    roll = [w for w in Worker.objects.all() if w.on_roll(day) or w.pk in records]

    if request.method == "POST" and not closed:
        if "holiday" in request.POST:
            return _mark_holiday(request, day, roll, records)
        problems, changes = [], []
        for worker in roll:
            status = request.POST.get(f"status_{worker.pk}", "")
            hours = _hours(request.POST.get(f"ot_{worker.pk}"))
            if status and status not in Attendance.Status.values:
                problems.append(f"{worker.name}: choose present, absent or half day.")
            elif hours is None:
                problems.append(f"{worker.name}: overtime has to be hours, from 0 to {MOST_OVERTIME:g}.")
            elif status == Attendance.Status.ABSENT and hours:
                problems.append(f"{worker.name} is marked absent but has overtime. Mark them present, or clear the overtime.")
            else:
                changes.append((worker, status or (Attendance.Status.PRESENT if hours else ""), hours))
        if problems:
            for problem in problems:
                messages.error(request, problem)
        else:
            with transaction.atomic():
                for worker, status, hours in changes:
                    if status:
                        Attendance.objects.update_or_create(
                            worker=worker, date=day,
                            defaults={"status": status, "overtime_hours": hours, "marked_by": request.user},
                        )
                    else:
                        Attendance.objects.filter(worker=worker, date=day).delete()
            marked = sum(1 for _, status, _ in changes if status)
            messages.success(request, f"Attendance for {day:%A, %d %b %Y} saved — {marked} of {len(roll)} marked.")
            return redirect(f"{reverse('monitoring:attendance')}?date={day.isoformat()}")
        # Show what they chose, with the problems, rather than what was saved.
        records = {
            worker.pk: Attendance(worker=worker, date=day, status=request.POST.get(f"status_{worker.pk}", ""),
                                  overtime_hours=_hours(request.POST.get(f"ot_{worker.pk}")) or ZERO)
            for worker in roll
        }
    elif request.method == "POST":
        messages.error(request, f"{month:%B %Y} is closed. Reopen it under Reports to correct it.")

    rows = [{"worker": worker, "record": records.get(worker.pk)} for worker in roll]
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


# ---------------------------------------------------------------- salary and advances
@admin_only
def salary(request):
    month = min(months.parse(request.GET.get("month"), months.this_month()), months.this_month())
    rows = [{"worker": worker, "advance": months.advance_table(worker, month)} for worker in months.workers_for(month)]
    return render(
        request,
        "monitoring/salary.html",
        {
            "month": month,
            "rows": rows,
            "closed": months.is_closed(month),
            "previous_month": months.previous_month(month),
            "next_month": months.next_month(month) if month < months.this_month() else None,
        },
    )


@admin_only
def salary_employee(request, pk):
    worker = get_object_or_404(Worker, pk=pk)
    month = min(months.parse(request.GET.get("month") or request.POST.get("month"), months.this_month()), months.this_month())
    closed = months.is_closed(month)
    table = months.advance_table(worker, month)
    row = Advance.objects.filter(worker=worker, month=month).first() or Advance(worker=worker, month=month)
    form = AdvanceForm(request.POST or None, instance=row, previous=table.previous)
    if request.method == "POST":
        if closed:
            messages.error(request, f"{month:%B %Y} is closed. Reopen it under Reports to correct it.")
            return redirect(f"{reverse('monitoring:salary_employee', args=[pk])}?month={month:%Y-%m}")
        if form.is_valid():
            saved = form.save(commit=False)
            saved.worker, saved.month, saved.updated_by = worker, month, request.user
            saved.save()
            messages.success(request, f"{worker.name}'s advances for {month:%B %Y} saved.")
            return redirect(f"{reverse('monitoring:salary_employee', args=[pk])}?month={month:%Y-%m}")

    # Month by month, newest first: the same four figures for each.
    history, shown = [], months.this_month()
    earliest = min([months.first_month(), month])
    while shown >= earliest:
        history.append({"month": shown, "table": months.advance_table(worker, shown)})
        shown = months.previous_month(shown)
    history = [item for item in history if item["month"] == month or item["table"].received or item["table"].deducted]
    return render(
        request,
        "monitoring/salary_employee.html",
        {"worker": worker, "month": month, "form": form, "table": table, "closed": closed, "history": history},
    )


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
            "workers": months.workers_for(month) if ready else [],
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
def _where(request):
    """The location sent from the phone, or an error to show."""
    try:
        data = json.loads(request.body or b"{}")
        latitude = Decimal(str(data["latitude"])).quantize(Decimal("0.000001"))
        longitude = Decimal(str(data["longitude"])).quantize(Decimal("0.000001"))
        accuracy = data.get("accuracy")
        accuracy = max(0, min(int(float(accuracy)), 100000)) if accuracy is not None else None
    except (ValueError, KeyError, TypeError, InvalidOperation):
        return None, "The phone did not send a location. Allow location for this app and try again."
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None, "That location is not on the map."
    return {"latitude": latitude, "longitude": longitude, "accuracy": accuracy, "data": data}, ""


@sales_only
def work(request):
    today = timezone.localdate()
    day = WorkDay.objects.filter(user=request.user, date=today).first()
    return render(
        request,
        "monitoring/work.html",
        {"day": day, "stops": day.stops.all() if day else [], "today": today},
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
    return JsonResponse({"ok": True, "started": f"{timezone.localtime(day.started_at):%I:%M %p}", "new": created})


@sales_only
@require_POST
def work_stop(request):
    where, problem = _where(request)
    if problem:
        return JsonResponse({"ok": False, "error": problem}, status=400)
    remark = " ".join(str(where["data"].get("remark") or "").split())
    if not remark:
        return JsonResponse({"ok": False, "error": "Write a remark about this site."}, status=400)
    if len(remark) > 1000:
        return JsonResponse({"ok": False, "error": "Keep the remark under 1000 characters."}, status=400)
    day = WorkDay.objects.filter(user=request.user, date=timezone.localdate()).first()
    if day is None:
        return JsonResponse({"ok": False, "error": "Start today's work first."}, status=400)
    stop = SiteStop.objects.create(user=request.user, workday=day, latitude=where["latitude"], longitude=where["longitude"],
                                   accuracy=where["accuracy"], remark=remark)
    return JsonResponse({"ok": True, "count": day.stops.count(), "at": f"{timezone.localtime(stop.recorded_at):%I:%M %p}"})


@members
def status(request):
    """Every site stop, with where it was and the remark. A sales executive sees their own."""
    today = timezone.localdate()
    start = parse_date(request.GET.get("from", "") or "") or today - timedelta(days=6)
    end = parse_date(request.GET.get("to", "") or "") or today
    if start > end:
        start, end = end, start
    people = User.objects.filter(role=Role.SALESPERSON).order_by("first_name", "username")
    person = None
    if request.user.is_super_admin:
        picked = request.GET.get("salesperson", "")
        person = next((p for p in people if str(p.pk) == picked), None)
    else:
        person = request.user

    stops = SiteStop.objects.filter(recorded_at__date__gte=start, recorded_at__date__lte=end).select_related("user")
    days = WorkDay.objects.filter(date__gte=start, date__lte=end).select_related("user")
    if person is not None:
        stops, days = stops.filter(user=person), days.filter(user=person)

    entries = [
        {"kind": "start", "user": day.user, "at": day.started_at, "latitude": day.latitude, "longitude": day.longitude,
         "accuracy": day.accuracy, "remark": "Started the day's work"}
        for day in days
    ] + [
        {"kind": "stop", "user": stop.user, "at": stop.recorded_at, "latitude": stop.latitude, "longitude": stop.longitude,
         "accuracy": stop.accuracy, "remark": stop.remark}
        for stop in stops
    ]
    entries.sort(key=lambda entry: entry["at"], reverse=True)
    return render(
        request,
        "monitoring/status.html",
        {
            "entries": entries,
            "people": people if request.user.is_super_admin else [],
            "person": person,
            "start": start,
            "end": end,
            "today": today,
            "stops_count": sum(1 for e in entries if e["kind"] == "stop"),
        },
    )
