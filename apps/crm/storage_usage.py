"""How full the document bucket is, and telling the Super Admin before it is.

A free storage plan is small, and when it fills, uploads stop working — on the
day a customer's signed paperwork is in someone's hand. The host emails an
account's owner about this, but only the owner, only if that inbox is watched,
and not in words that mention this software. The Super Admin is in the app
every day, so the warning goes there: a bar on the dashboard, a banner across
every page once it is nearly full, and a notification in the bell.

The size comes from asking the bucket, not from adding up rows in the database,
because the database does not know how big a file is and the bucket does.
Listing a bucket returns a thousand files a call, so a few thousand documents
cost a handful of quick calls — made at most once an hour, and never for anyone
but the Super Admin. Any trouble reaching it simply hides the bar; a slow or
failing bucket must not slow or break a page.
"""

import logging
from datetime import timedelta

import boto3
from botocore.config import Config
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

CACHE_KEY = "storage-usage"
FRESH_FOR = 60 * 60          # a size an hour old is plenty for a slow-filling bucket
RETRY_AFTER = 5 * 60         # after a failure, do not try again on every page
REMIND_EVERY = timedelta(days=7)
MESSAGE_START = "Document storage is"


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL or None,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
        config=Config(
            signature_version=settings.AWS_S3_SIGNATURE_VERSION,
            s3={"addressing_style": settings.AWS_S3_ADDRESSING_STYLE},
            # Short, so a struggling bucket costs a page a few seconds at worst.
            connect_timeout=3,
            read_timeout=8,
            retries={"max_attempts": 1},
        ),
    )


def _level(percent):
    if percent >= settings.STORAGE_CRITICAL_PERCENT:
        return "critical"
    if percent >= settings.STORAGE_WARN_PERCENT:
        return "warn"
    return "ok"


def _mb(value):
    """8.5 MB, 412 MB, 1 GB — as many digits as a person would say aloud."""
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:,.1f}".rstrip("0").rstrip(".") + " GB"
    megabytes = value / 1_000_000
    return f"{megabytes:,.0f} MB" if megabytes >= 100 else f"{megabytes:,.1f}".rstrip("0").rstrip(".") + " MB"


def measure():
    """Ask the bucket. Returns a dict, or None if it cannot be reached."""
    used = files = 0
    paginator = _client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.AWS_STORAGE_BUCKET_NAME):
        for item in page.get("Contents", []):
            used += item["Size"]
            files += 1

    limit = settings.STORAGE_LIMIT_MB * 1_000_000
    percent = used * 100 / limit if limit else 0
    return {
        "used": used,
        "limit": limit,
        "percent": percent,
        "percent_bar": min(100, round(percent)),
        "files": files,
        "level": _level(percent),
        "used_label": _mb(used),
        "limit_label": _mb(limit),
    }


def current():
    """The latest size, or None when there is no bucket or it cannot be reached."""
    if not settings.AWS_STORAGE_BUCKET_NAME:
        return None  # files are on the server's own disk; nothing to meter here

    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached or None  # False is a remembered failure

    try:
        usage = measure()
    except Exception:
        logger.warning("Could not read the document bucket's size", exc_info=True)
        cache.set(CACHE_KEY, False, RETRY_AFTER)
        return None

    cache.set(CACHE_KEY, usage, FRESH_FOR)
    # Only on a fresh measurement, so a cached page load does no extra work.
    tell_super_admins(usage)
    return usage


def tell_super_admins(usage):
    """A bell notification per level, repeated weekly while it stays that full.

    Each level is remembered on its own, so a "getting full" notice sent on
    Monday does not hide the "nearly full" one that follows on Thursday.
    """
    if not usage or usage["level"] == "ok":
        return

    from apps.accounts.models import User

    from .models import Notification

    if usage["level"] == "critical":
        advice = "Uploads will stop when it is full. Upgrade the plan or move to a bigger bucket now."
    else:
        advice = "When it is full, uploads stop. Time to plan an upgrade or a bigger bucket."

    admins = User.objects.filter(role="super_admin", is_active=True)
    already = set(
        Notification.objects.filter(
            message__startswith=MESSAGE_START,
            message__contains=advice,
            created_at__gte=timezone.now() - REMIND_EVERY,
        ).values_list("user_id", flat=True)
    )
    message = f"{MESSAGE_START} {usage['percent']:.0f}% full ({usage['used_label']} of {usage['limit_label']}). {advice}"

    Notification.objects.bulk_create(
        [Notification(user=admin, message=message[:255]) for admin in admins if admin.pk not in already]
    )
