"""Reminders that go out on a clock rather than because someone did something.

The app has no scheduler — on the free host it sleeps between visits — so these
are checked as people use it: at most every few minutes, from whichever page is
opened. Each one records the day it went out, so however many people are signed
in at once, it goes once a day.
"""

from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from . import queues, updates
from .models import Lead

# A site still not marked installed this many days after dispatch is chased, daily.
INSTALL_LATE_AFTER_DAYS = 3


def installations_late(today=None):
    """Remind everyone on the installation step about each site that is late. Returns how many."""
    today = today or timezone.localdate()
    cutoff = today - timedelta(days=INSTALL_LATE_AFTER_DAYS)
    # Dispatched on the cutoff day or before, in India time.
    before = timezone.make_aware(datetime.combine(cutoff + timedelta(days=1), time.min))
    not_today = Q(installation_reminded_on__isnull=True) | Q(installation_reminded_on__lt=today)
    late = queues.installation().filter(not_today, dispatched_at__lt=before)

    people, sent = None, 0
    for lead in late:
        # Claimed here, so two pages opened at once cannot both send it.
        if not Lead.objects.filter(not_today, pk=lead.pk).update(installation_reminded_on=today):
            continue
        if people is None:
            people = queues.installation_people()
        days = (today - timezone.localtime(lead.dispatched_at).date()).days
        # Yesterday's reminder about the same site is replaced by today's, not piled on it.
        updates.clear(updates.INSTALL, lead=lead)
        updates.send(
            people,
            f"Installation not marked complete — {lead.customer_name}, {lead.site_location}: dispatched {days} days ago",
            lead=lead,
            topic=updates.INSTALL,
        )
        sent += 1
    return sent


def check(now_and_then=True):
    """Send whatever is due. Throttled, since it runs as pages are opened."""
    if now_and_then and not cache.add("reminders-checked", True, settings.REMINDER_CHECK_SECONDS):
        return 0
    return installations_late()
