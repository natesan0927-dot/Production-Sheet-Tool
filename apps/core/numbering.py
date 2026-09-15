"""
Central document numbering: LEAD-2026-00001, QUO-2026-00045, ORD-2026-00001, ...

Formats are stored in NumberSequence (editable from Admin Settings) rather than
hard-coded, per spec section 61.
"""

from django.db import transaction
from django.utils import timezone

from apps.core.models import NumberSequence

DEFAULT_PREFIXES = {
    "customer": "CUS",
    "lead": "LEAD",
    "measurement": "MEA",
    "final_measurement": "FMEA",
    "quotation": "QUO",
    "order": "ORD",
    "production_sheet": "PRD",
    "dispatch": "DSP",
    "installation": "INS",
    "warranty": "WAR",
    "complaint": "SRV",
    "task": "TSK",
}


@transaction.atomic
def get_next_number(doc_type: str) -> str:
    """Return the next formatted number for a document type, e.g. 'LEAD-2026-00001'."""
    year = timezone.now().year
    prefix = DEFAULT_PREFIXES.get(doc_type, doc_type.upper()[:6])

    seq, created = NumberSequence.objects.select_for_update().get_or_create(
        doc_type=doc_type,
        defaults={"prefix": prefix, "year": year, "last_number": 0, "padding": 5},
    )

    if not created and seq.year != year:
        # New calendar year: restart the running number, keep the admin-configured prefix.
        seq.year = year
        seq.last_number = 0

    seq.last_number += 1
    seq.save(update_fields=["year", "last_number"])

    return f"{seq.prefix}-{seq.year}-{str(seq.last_number).zfill(seq.padding)}"
