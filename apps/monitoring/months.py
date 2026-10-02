"""Months: when one closes, and what a worker's month adds up to.

A month is open for marking and editing until the 1st of the next, when it
closes by itself and its report is ready. The Super Admin can open a closed
month again to correct it, and close it again after.

The advance table, for one worker and one month:

    received this month   = every advance given on a day of the month (entered
                            beside that day's attendance)
    previous advance      = what they still owed coming into the month — last
                            month's remaining: the advance outstanding when they
                            were added here, plus every earlier advance, less
                            every earlier month's deduction
    deducted this month   = the amount entered when the month's report is downloaded
    remaining             = previous + received this month − deducted
    salary to be paid     = monthly salary − deducted this month
"""

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from .models import ZERO, Advance, Attendance, DayAdvance, ReopenedMonth, Worker


def first_of(day):
    return day.replace(day=1)


def next_month(month):
    return (month.replace(day=28) + timedelta(days=4)).replace(day=1)


def previous_month(month):
    return (month - timedelta(days=1)).replace(day=1)


def last_day(month):
    return month.replace(day=calendar.monthrange(month.year, month.month)[1])


def this_month():
    return first_of(timezone.localdate())


def parse(text, default=None):
    """'2026-09' (or a full date) to the 1st of that month."""
    try:
        year, month = (int(part) for part in str(text).split("-")[:2])
        return date(year, month, 1)
    except (TypeError, ValueError):
        return default


def is_closed(month):
    """Closed from the 1st of the next month, unless the Super Admin opened it again."""
    return month < this_month() and not ReopenedMonth.objects.filter(month=month).exists()


def is_reopened(month):
    return ReopenedMonth.objects.filter(month=month).exists()


def last_closed():
    """The month whose report is the latest one ready."""
    return previous_month(this_month())


def first_month():
    """The earliest month with anything recorded, for lists of months."""
    starts = [
        Attendance.objects.order_by("date").values_list("date", flat=True).first(),
        DayAdvance.objects.order_by("date").values_list("date", flat=True).first(),
    ]
    added = Worker.objects.order_by("created_at").values_list("created_at", flat=True).first()
    if added:
        starts.append(timezone.localtime(added).date())
    starts = [start for start in starts if start]
    return first_of(min(starts)) if starts else this_month()


def closed_months():
    """Every month with a report ready, newest first."""
    months, month, earliest = [], last_closed(), first_month()
    while month >= earliest:
        months.append(month)
        month = previous_month(month)
    return months


def covers(worker, month):
    """Whether a month is any of this worker's business: they were on the roll, or something was recorded."""
    if month is None or month >= this_month():
        return False
    end = last_day(month)
    if Attendance.objects.filter(worker=worker, date__gte=month, date__lte=end).exists():
        return True
    if DayAdvance.objects.filter(worker=worker, date__gte=month, date__lte=end).exists():
        return True
    added = timezone.localtime(worker.created_at).date()
    started = max(filter(None, [worker.joined_on, added]))
    return started <= end and (worker.is_active or (worker.left_on and worker.left_on > month))


def workers_for(month):
    """Everyone on the roll at some point in the month, or with something recorded in it."""
    end = last_day(month)
    with_records = set(Attendance.objects.filter(date__gte=month, date__lte=end).values_list("worker_id", flat=True))
    with_records |= set(DayAdvance.objects.filter(date__gte=month, date__lte=end).values_list("worker_id", flat=True))
    return [
        worker for worker in Worker.objects.all()
        if worker.pk in with_records
        or ((not worker.joined_on or worker.joined_on <= end) and (worker.is_active or (worker.left_on and worker.left_on > month)))
    ]


# ---------------------------------------------------------------- one worker's month
@dataclass
class AdvanceTable:
    received: Decimal = ZERO
    previous: Decimal = ZERO
    deducted: Decimal = ZERO
    salary: Decimal = ZERO
    # Whether a deduction has been entered for the month yet (at the report).
    settled: bool = False
    given: list = field(default_factory=list)   # [(date, amount)] this month

    @property
    def owed(self):
        """Everything they owe before this month's deduction."""
        return self.previous + self.received

    @property
    def remaining(self):
        return self.owed - self.deducted

    @property
    def salary_to_pay(self):
        return self.salary - self.deducted


@dataclass
class MonthFigures:
    worker: Worker
    month: date
    present: int = 0
    absent: int = 0
    half: int = 0
    holiday: int = 0
    unmarked: int = 0
    overtime_hours: Decimal = ZERO
    overtime_days: list = field(default_factory=list)      # [(date, hours)]
    days: dict = field(default_factory=dict)               # date -> Attendance
    advance: AdvanceTable = field(default_factory=AdvanceTable)

    @property
    def advances_by_day(self):
        return dict(self.advance.given)

    @property
    def days_worked(self):
        """Full days plus half of each half day."""
        return Decimal(self.present) + Decimal(self.half) / 2

    @property
    def overtime_dates(self):
        """'03, 07, 15' — the dates of the month with overtime."""
        return ", ".join(f"{day:%d}" for day, _ in self.overtime_days)


def advance_table(worker, month):
    end = last_day(month)
    given_before = DayAdvance.objects.filter(worker=worker, date__lt=month).aggregate(t=Sum("amount"))["t"] or ZERO
    deducted_before = Advance.objects.filter(worker=worker, month__lt=month).aggregate(t=Sum("deduction"))["t"] or ZERO
    given = [(a.date, a.amount) for a in DayAdvance.objects.filter(worker=worker, date__gte=month, date__lte=end)]
    row = Advance.objects.filter(worker=worker, month=month).first()
    return AdvanceTable(
        received=sum((amount for _, amount in given), ZERO),
        previous=worker.opening_advance + given_before - deducted_before,
        deducted=row.deduction if row else ZERO,
        salary=worker.monthly_salary,
        settled=row is not None,
        given=given,
    )


def figures(worker, month):
    """Attendance and advances for one worker's month."""
    end = last_day(month)
    result = MonthFigures(worker=worker, month=month, advance=advance_table(worker, month))
    for record in Attendance.objects.filter(worker=worker, date__gte=month, date__lte=end):
        result.days[record.date] = record
        setattr(result, record.status, getattr(result, record.status) + 1)
        if record.overtime_hours:
            result.overtime_hours += record.overtime_hours
            result.overtime_days.append((record.date, record.overtime_hours))
    # Days that should have been marked by now and were not.
    today = timezone.localdate()
    day = month
    while day <= min(end, today):
        if day not in result.days and worker.on_roll(day):
            result.unmarked += 1
        day += timedelta(days=1)
    return result


def calendar_weeks(month, days, advances=None):
    """Weeks of the month, Monday first: each a list of (date or None, Attendance or None, advance or None)."""
    advances = advances or {}
    weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(month.year, month.month):
        weeks.append([(day, days.get(day), advances.get(day)) if day.month == month.month else (None, None, None)
                      for day in week])
    return weeks
