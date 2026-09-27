"""Take the demo logins and their sample leads out of a database.

    python manage.py remove_demo_data

Safe to run on a live site and safe to run twice. It removes only what belongs
to the demo accounts — those logins and the leads sitting under them — and
leaves every real user and every real lead alone. reset_to_live wipes
everything; this does not.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User
from apps.crm.models import Lead

from .seed_data import DEMO_USERS

DEMO_USERNAMES = [username for username, *_ in DEMO_USERS]


def remove_demo_data():
    """Returns (logins removed, leads removed)."""
    demo_users = User.objects.filter(username__in=DEMO_USERNAMES)
    logins = demo_users.count()
    if not logins:
        return 0, 0

    # A lead cannot outlive the person it is assigned to, so the sample leads
    # have to go first — and with them their follow-ups and anything else that
    # hangs off a lead. Their notifications, tasks and targets go with the
    # login itself.
    leads = Lead.objects.filter(assigned_to__in=demo_users)
    lead_count = leads.count()
    with transaction.atomic():
        leads.delete()
        demo_users.delete()
    return logins, lead_count


class Command(BaseCommand):
    help = "Remove the demo logins and the sample leads under them, leaving real data alone."

    def handle(self, *args, **options):
        logins, leads = remove_demo_data()
        if logins:
            self.stdout.write(self.style.SUCCESS(f"Removed {logins} demo login(s) and {leads} sample lead(s)."))
        else:
            self.stdout.write("No demo accounts here — nothing to remove.")
