"""Bring the leads over from the old CRM and book a follow-up on each.

    python manage.py import_old_crm --dry-run     to see what it would do
    python manage.py import_old_crm               to do it

Reads apps/crm/management/data/old_crm_leads.psv (the old CRM's export, without its
Won orders) and creates one open lead per row, each with one follow-up on
--followup-date (default 2026-10-06, 9:00 am). Safe to run more than once: a lead
carries "[Imported from old CRM #<id> ...]" in its remarks, and any row already
carrying it is left alone.

How the old columns land:
    Work Status "Quoted" / "Negotiation in Progress"  -> quotation sent (open, in the
        follow-up stage, with the quote number); "Visited" / "Yet to Visit" -> waiting
        for a quotation
    site stage Brick / Plastering / Ready             -> Brick Work / Plastering / Ready
    sales executive                                   -> Sales Executive (matched by first name)
    First Submitted / Last Updated                    -> created / last updated
The old CRM kept no site location or lead source, so those read "To be updated" and
"Others — Old CRM".
"""

import csv
import re
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Role, User
from apps.crm.models import FollowUp, Lead

DEFAULT_FILE = Path(__file__).resolve().parent.parent / "data" / "old_crm_leads.psv"
IST = ZoneInfo("Asia/Kolkata")

SITE_STAGES = {"Brick": "brickwork", "Plastering": "plastering", "Ready": "ready"}
# Statuses where a quotation had already gone out in the old CRM.
QUOTED = {"Quoted", "Negotiation in Progress"}


def stamp(text):
    return datetime.strptime(text, "%d %b %Y %I:%M %p").replace(tzinfo=IST)


def marker(old_id):
    return f"[Imported from old CRM #{old_id} "


class Command(BaseCommand):
    help = "Import the old CRM's leads and schedule a follow-up for each."

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(DEFAULT_FILE), help="Pipe-separated export to read.")
        parser.add_argument("--followup-date", default="2026-10-06", help="YYYY-MM-DD (default 2026-10-06).")
        parser.add_argument("--dry-run", action="store_true", help="Check everything and change nothing.")

    def handle(self, *args, **options):
        try:
            followup_date = date.fromisoformat(options["followup_date"])
        except ValueError:
            raise CommandError("--followup-date must look like 2026-10-06.")

        with open(options["file"], newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle, delimiter="|"))

        executives = self.executives(rows)
        problems = self.check(rows)
        if problems:
            raise CommandError("Nothing was imported:\n  " + "\n  ".join(problems))

        already = set()
        for remarks in Lead.objects.filter(remarks__contains="[Imported from old CRM #").values_list("remarks", flat=True):
            already.update(re.findall(r"\[Imported from old CRM #(\d+) ", remarks))

        created = skipped = 0
        with transaction.atomic():
            # Oldest first, so the new lead numbers follow the order they were first entered.
            for row in sorted(rows, key=lambda r: stamp(r["first_submitted"])):
                if row["id"] in already:
                    skipped += 1
                    continue
                if not options["dry_run"]:
                    self.create(row, executives[row["executive"].lower()], followup_date)
                created += 1
            self.stdout.write(
                f"{'Would import' if options['dry_run'] else 'Imported'} {created} lead(s), "
                f"each with a follow-up on {followup_date:%d %b %Y}; {skipped} already there, left alone."
            )

    def executives(self, rows):
        """The sales executives the file names, by first name — all of them must have accounts."""
        names = {row["executive"].strip().lower() for row in rows}
        found = {}
        for person in User.objects.filter(role=Role.SALESPERSON, is_active=True):
            found.setdefault(person.first_name.lower(), person)
        missing = sorted(names - found.keys())
        if missing:
            raise CommandError(
                f"No active Sales Executive named {', '.join(missing)}. "
                "Run `python manage.py seed_employees` first, or fix the names."
            )
        return {name: found[name] for name in names}

    def check(self, rows):
        problems, seen = [], set()
        for row in rows:
            tag = f"#{row['id']} {row['customer']}"
            if row["id"] in seen:
                problems.append(f"{tag}: listed twice")
            seen.add(row["id"])
            if row["stage"] not in SITE_STAGES:
                problems.append(f"{tag}: unknown site stage {row['stage']!r}")
            if not re.fullmatch(r"\d{10}", row["phone"]):
                problems.append(f"{tag}: phone {row['phone']!r} is not 10 digits")
            if not row["qty"].isdigit():
                problems.append(f"{tag}: quantity {row['qty']!r} is not a number")
            for column in ("first_submitted", "last_updated"):
                try:
                    stamp(row[column])
                except ValueError:
                    problems.append(f"{tag}: {column} {row[column]!r} is not a date")
        return problems

    def create(self, row, executive, followup_date):
        created_at, updated_at = stamp(row["first_submitted"]), stamp(row["last_updated"])
        customer = row["customer"].strip()
        project = row["project"].strip()
        remarks = row["remarks"].strip()
        note = f"{marker(row['id'])}— {row['status']}]"

        lead = Lead(
            customer_name=customer,
            phone=row["phone"],
            project_name="" if project.lower() == customer.lower() else project,
            site_location="To be updated",
            lead_source="other",
            lead_source_other="Old CRM",
            assigned_to=executive,
            created_by=executive,
            approx_quantity=int(row["qty"]),
            site_stage=SITE_STAGES[row["stage"]],
            remarks=f"{remarks}\n{note}" if remarks else note,
        )
        if row["status"] in QUOTED:
            # The quotation went out in the old CRM, so the lead joins the new one at the
            # follow-up stage; the stage marks below are what put it there.
            lead.measurement_mode = Lead.MeasurementMode.TEXT
            lead.measurement_notes = "Measured and quoted in the old CRM."
            lead.measurement_done_at = created_at
            lead.quotation_number = row["quote"]
            lead.quotation_uploaded_at = created_at
        lead.save()

        FollowUp.objects.create(
            lead=lead,
            date=followup_date,
            time=time(9, 0),
            note="Follow-up after the move from the old CRM",
            created_by=executive,
        )
        # auto_now_add / auto_now would stamp today; keep the old CRM's dates instead.
        Lead.objects.filter(pk=lead.pk).update(created_at=created_at, updated_at=updated_at)
