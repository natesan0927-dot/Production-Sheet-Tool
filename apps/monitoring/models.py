"""Monitoring: the factory's attendance and pay advances, and the sales executives' days out.

Separate from the CRM. The people whose attendance is kept are the factory's
employees; they do not sign in. Only the Super Admin keeps their records, and
only the Super Admin and the sales executives can open Monitoring at all.

Everything is kept in the database. A worker marked every day is about 365 small
rows a year, so thirty workers come to roughly a megabyte a year. Reports are
drawn when downloaded and never stored.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

ZERO = Decimal("0")


class Worker(models.Model):
    """Someone on the factory's payroll whose attendance and advances are kept here."""

    name = models.CharField(max_length=150)
    phone = models.CharField("Mobile number", max_length=20, blank=True)
    designation = models.CharField(max_length=80, blank=True, help_text="Fabricator, helper, installer, driver…")
    joined_on = models.DateField("Date of joining", null=True, blank=True)
    monthly_salary = models.DecimalField(max_digits=12, decimal_places=2)
    # What they already owed when they were added here, so the running balance starts right.
    opening_advance = models.DecimalField(
        "Advance already outstanding", max_digits=12, decimal_places=2, default=ZERO,
        help_text="Advance they had already taken and not yet repaid when added here. Leave 0 if none.",
    )
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    # Removed, not deleted, so the months they worked still add up.
    is_active = models.BooleanField(default=True)
    left_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [Lower("name"), "pk"]

    def __str__(self):
        return self.name

    def on_roll(self, day):
        """Whether attendance is kept for them on this day."""
        if self.joined_on and day < self.joined_on:
            return False
        return self.is_active or (self.left_on is not None and day < self.left_on)


class Attendance(models.Model):
    """One worker, one day: whether they came, and any overtime."""

    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        HALF = "half", "Half day"
        HOLIDAY = "holiday", "Holiday"

    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices)
    # Worked beyond the day, in hours. Can go with a holiday (Sunday overtime), never with an absence.
    overtime_hours = models.DecimalField(max_digits=4, decimal_places=1, default=ZERO)
    marked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date"]
        constraints = [models.UniqueConstraint(fields=["worker", "date"], name="one_attendance_per_worker_per_day")]
        indexes = [models.Index(fields=["date"])]

    def __str__(self):
        return f"{self.worker} {self.date}: {self.get_status_display()}"


class DayAdvance(models.Model):
    """Money advanced to a worker on a day — a weekly advance, a monthly one, whatever was given.

    Entered beside the day's attendance. A month's advances are the sum of its days.
    """

    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name="day_advances")
    date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    given_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date"]
        constraints = [models.UniqueConstraint(fields=["worker", "date"], name="one_advance_per_worker_per_day")]

    def __str__(self):
        return f"{self.worker} {self.date}: {self.amount}"


class Advance(models.Model):
    """What was recovered from a worker's salary for one month's advances.

    Entered when the month's report is downloaded.
    """

    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name="advances")
    month = models.DateField(help_text="The 1st of the month.")
    deduction = models.DecimalField("Amount to deduct", max_digits=12, decimal_places=2, default=ZERO)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["month"]
        constraints = [models.UniqueConstraint(fields=["worker", "month"], name="one_advance_row_per_worker_per_month")]

    def __str__(self):
        return f"{self.worker} {self.month:%b %Y}"


class ReopenedMonth(models.Model):
    """A finished month opened again by the Super Admin to correct it.

    A month closes by itself on the 1st of the next, when its report is ready.
    """

    month = models.DateField(unique=True)
    reopened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    reopened_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.month:%B %Y} reopened"


class WorkDay(models.Model):
    """A sales executive's day out: when and where they started, and when they finished."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workdays")
    date = models.DateField(default=timezone.localdate)
    started_at = models.DateTimeField(default=timezone.now)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    accuracy = models.PositiveIntegerField("Accurate to (metres)", null=True, blank=True)
    # The area it was in, looked up from the coordinates ("Anna Nagar, Chennai").
    place = models.CharField(max_length=200, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    end_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    end_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    end_accuracy = models.PositiveIntegerField(null=True, blank=True)
    end_place = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-date"]
        constraints = [models.UniqueConstraint(fields=["user", "date"], name="one_workday_per_person_per_day")]

    def __str__(self):
        return f"{self.user} {self.date}"


class SiteStop(models.Model):
    """A site a sales executive stopped at: where they were, and what they noted."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="site_stops")
    workday = models.ForeignKey(WorkDay, on_delete=models.CASCADE, related_name="stops")
    recorded_at = models.DateTimeField(default=timezone.now)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    accuracy = models.PositiveIntegerField("Accurate to (metres)", null=True, blank=True)
    place = models.CharField(max_length=200, blank=True)
    remark = models.TextField(max_length=1000)

    class Meta:
        ordering = ["-recorded_at"]
        indexes = [models.Index(fields=["user", "recorded_at"])]

    def __str__(self):
        return f"{self.user} {self.recorded_at:%d %b %H:%M}"
