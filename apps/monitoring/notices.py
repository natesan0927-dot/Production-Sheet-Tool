"""Telling the Super Admin, on the 1st, that last month's attendance report is ready."""

import logging

from django.conf import settings
from django.core.cache import cache
from django.urls import reverse

logger = logging.getLogger(__name__)


def report_ready(request):
    """Once a month, as the Super Admin uses the app: the report for the month just closed is ready."""
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated and user.is_super_admin) or request.path in ("/sw.js", "/offline/"):
        return {}
    try:
        _announce()
    except Exception:  # a notice must never break the page someone opened
        logger.warning("Could not announce the attendance report", exc_info=True)
    return {}


def _announce():
    from apps.accounts.models import Role, User
    from apps.crm import updates
    from apps.crm.models import Notification

    from . import months

    month = months.last_closed()
    # Looked into at most every few minutes, however many pages the Super Admin opens.
    if not cache.add(f"attendance-report-checked-{month:%Y-%m}", True, settings.REMINDER_CHECK_SECONDS):
        return
    topic = f"attendance-report:{month:%Y-%m}"
    if month < months.first_month() or not months.workers_for(month) or Notification.objects.filter(topic=topic).exists():
        return
    admins = User.objects.filter(role=Role.SUPER_ADMIN, is_active=True)
    updates.send(
        admins,
        f"The attendance report for {month:%B %Y} is ready — an Excel sheet for everyone, and a PDF for each employee.",
        topic=topic,
        link=f"{reverse('monitoring:reports')}?month={month:%Y-%m}",
    )
