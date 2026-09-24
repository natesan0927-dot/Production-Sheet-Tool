"""Clear everything the demo left behind and leave a site ready to go live.

    python manage.py reset_to_live

Removes every lead and all the work hanging off one — files, follow-ups,
payments, tasks, notifications, complaints, targets — and the demo accounts.
Then creates the real staff. It asks before it does any of it, because it
cannot be undone.

    python manage.py reset_to_live --noinput     to skip the question
    python manage.py reset_to_live --keep-leads  to clear the demo logins only
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.crm.models import (
    FollowUp,
    Lead,
    Notification,
    SalesTarget,
    ServiceComplaint,
    Task,
)

DEMO_USERNAMES = [
    "demo_sales1", "demo_sales2", "demo_measure", "demo_quotation",
    "demo_accounts", "demo_production", "demo_field", "demo_admin",
]


class Command(BaseCommand):
    help = "Wipe the demo data and create the real staff accounts."

    def add_arguments(self, parser):
        parser.add_argument("--noinput", action="store_true", help="Do not ask first.")
        parser.add_argument("--keep-leads", action="store_true", help="Only remove the demo logins.")

    def handle(self, *args, **options):
        leads = Lead.objects.count()
        demo = User.objects.filter(username__in=DEMO_USERNAMES).count()

        self.stdout.write("This will permanently remove:")
        if not options["keep_leads"]:
            self.stdout.write(f"  {leads} lead(s) and every file, follow-up, payment and task on them")
            self.stdout.write(f"  {Notification.objects.count()} notification(s), {SalesTarget.objects.count()} target(s)")
        self.stdout.write(f"  {demo} demo login(s)")

        if not options["noinput"]:
            if input("\nType 'yes' to go ahead: ").strip().lower() != "yes":
                raise CommandError("Nothing was changed.")

        with transaction.atomic():
            if not options["keep_leads"]:
                # Leads cascade to their files, follow-ups, payments, charges,
                # revisions, assignments and complaints.
                Lead.objects.all().delete()
                # These do not hang off a lead.
                Notification.objects.all().delete()
                Task.objects.all().delete()
                SalesTarget.objects.all().delete()
            User.objects.filter(username__in=DEMO_USERNAMES).delete()

        self.stdout.write(self.style.SUCCESS("Cleared."))
        self.stdout.write("")
        call_command("seed_employees")

        left = {
            "leads": Lead.objects.count(),
            "follow-ups": FollowUp.objects.count(),
            "complaints": ServiceComplaint.objects.count(),
            "users": User.objects.count(),
        }
        self.stdout.write("")
        self.stdout.write("Now on the site: " + ", ".join(f"{count} {name}" for name, count in left.items()))
