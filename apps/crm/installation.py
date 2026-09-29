"""Installers, and the sites each one has been given.

Installation is outsourced: production names the installer when a site is
dispatched, and accounts then pays them. Everything is grouped by the name typed
at dispatch, so the whole feature depends on that name being spelled the same way
every time. "Suresh", "suresh" and "Suresh " must land in one folder, not three,
which is why grouping ignores case and spacing and why the dispatch form reuses
the spelling already on file.
"""

import hashlib
from collections import defaultdict
from decimal import Decimal

from django.utils.text import slugify

from .models import Lead


def key_of(name):
    """The name with case and spacing removed, for deciding two spellings are one person."""
    return " ".join((name or "").lower().split())


def clean_name(name):
    """Tidy spacing, and reuse the spelling already on file if this is a known installer."""
    tidy = " ".join((name or "").split())
    if not tidy:
        return ""
    known = (
        Lead.objects.exclude(installation_person="")
        .filter(installation_person__iexact=tidy)
        .order_by("dispatched_at", "pk")
        .values_list("installation_person", flat=True)
        .first()
    )
    return known or tidy


def _old_slug(key):
    return slugify(key) or "installer"


def folder_slug_for(lead):
    """The address of the folder this site's installer keeps.

    The readable part alone is not enough: "S. Kumar" and "S Kumar" are two
    people but read the same once the dot is gone, and a name in Tamil has no
    letters an address can carry. A short tag worked out from the full name keeps
    every installer's address their own, and the same every time.
    """
    key = key_of(lead.installation_person)
    tag = hashlib.md5(key.encode("utf-8")).hexdigest()[:6]
    return f"{_old_slug(key)}-{tag}"


def installer_names():
    """Every distinct installer so far, once each, for the dispatch form's suggestions."""
    seen = {}
    for name in Lead.objects.exclude(installation_person="").values_list("installation_person", flat=True):
        seen.setdefault(key_of(name), " ".join(name.split()))
    return sorted(seen.values(), key=str.lower)


def dispatched_sites():
    return (
        Lead.objects.filter(status=Lead.Status.WON, dispatched_at__isnull=False)
        .exclude(installation_person="")
        .select_related("assigned_to")
        .prefetch_related("installer_payments")
        .order_by("dispatched_at", "pk")
    )


def _totals(sites):
    payable = sum((site.installation_charge or Decimal("0")) for site in sites)
    paid = sum((site.installer_paid for site in sites), Decimal("0"))
    return {
        "sites": len(sites),
        "sqft": sum((site.total_sqft or Decimal("0")) for site in sites),
        "payable": payable,
        "paid": paid,
        "balance": payable - paid,
        "unpriced": sum(1 for site in sites if site.installation_charge is None),
    }


def folders(query=""):
    """One folder per installer, biggest balance owed first."""
    grouped = defaultdict(list)
    for site in dispatched_sites():
        grouped[key_of(site.installation_person)].append(site)

    result = []
    for key, sites in grouped.items():
        name = " ".join(sites[0].installation_person.split())
        # "sites" is the count (from _totals); the leads themselves are under "leads".
        result.append({"name": name, "key": key, "slug": folder_slug_for(sites[0]), "leads": sites, **_totals(sites)})
    result.sort(key=lambda folder: (-folder["balance"], folder["name"].lower()))
    return matching(result, query)


def matching(found, query):
    """The folders whose installer, or one of whose sites, matches what was typed."""
    query = (query or "").strip().lower()
    if not query:
        return found
    return [
        folder for folder in found
        if query in folder["key"]
        or any(query in f"{site.customer_name} {site.project_name} {site.site_location}".lower() for site in folder["leads"])
    ]


def folder(slug):
    """One installer's folder by its address slug, or None."""
    every = folders()
    for candidate in every:
        if candidate["slug"] == slug:
            return candidate
    # An address saved before the tag was added still opens, while it is unambiguous.
    older = [candidate for candidate in every if _old_slug(candidate["key"]) == slug]
    return older[0] if len(older) == 1 else None
