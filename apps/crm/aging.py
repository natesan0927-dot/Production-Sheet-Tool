"""How long an invoice has been unpaid, and the ranges the accounts team asks for.

The ranges overlap on purpose — "0 to 30 days" contains "0 to 15 days" — because
they are what people ask for in conversation: "what is due within the month",
"what is really late". The ageing summary, which has to add up, uses the
separate bands below instead.
"""

# key, label, first day, last day (None = no upper limit). The keys travel in a
# web address, where "+" means a space, so they are plain letters and digits.
RANGES = [
    ("all", "All outstanding", 0, None),
    ("0-15", "0 to 15 days", 0, 15),
    ("0-30", "0 to 30 days", 0, 30),
    ("over30", "Above 30 days", 31, None),
]

# Separate bands, for a summary whose rows must add up to the total.
BANDS = [
    ("0 to 15 days", 0, 15),
    ("16 to 30 days", 16, 30),
    ("Above 30 days", 31, None),
]

_BY_KEY = {key: (label, low, high) for key, label, low, high in RANGES}


def clean_key(value):
    """Whatever came in the address bar, reduced to a range we know."""
    return value if value in _BY_KEY else "all"


def label(key):
    return _BY_KEY[clean_key(key)][0]


def contains(key, days):
    _, low, high = _BY_KEY[clean_key(key)]
    return days >= low and (high is None or days <= high)


def only_in_range(leads, key):
    """Invoiced, still-unpaid leads whose age falls in the range."""
    return [lead for lead in leads if lead.is_outstanding and contains(key, lead.overdue_days)]


def by_band(leads):
    """(band label, how many, how much) for each separate band."""
    rows = []
    for name, low, high in BANDS:
        inside = [
            lead
            for lead in leads
            if lead.is_outstanding and lead.overdue_days >= low and (high is None or lead.overdue_days <= high)
        ]
        rows.append((name, len(inside), sum((lead.balance_amount or 0) for lead in inside)))
    return rows
