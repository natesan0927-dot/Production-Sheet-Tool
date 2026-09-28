from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


def _group_indian(digits):
    """1500000 -> 15,00,000 (last three digits, then pairs)."""
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


@register.filter
def rupees(value, decimals=0):
    if value is None or value == "":
        return "—"
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return value
    sign = "-" if amount < 0 else ""
    amount = abs(amount).quantize(Decimal(1) if not decimals else Decimal("0.01"))
    whole, _, fraction = str(amount).partition(".")
    text = _group_indian(whole)
    if decimals:
        text = f"{text}.{fraction or '00'}"
    return f"{sign}₹{text}"


@register.filter
def rupees_short(value):
    """₹34.5 L, ₹1.2 Cr, ₹8,500 — the way a summary says a large amount aloud."""
    if value is None or value == "":
        return "—"
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return value
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if amount >= Decimal("10000000"):
        text = f"{amount / Decimal('10000000'):.2f}".rstrip("0").rstrip(".") + " Cr"
    elif amount >= Decimal("100000"):
        text = f"{amount / Decimal('100000'):.1f}".rstrip("0").rstrip(".") + " L"
    else:
        text = _group_indian(str(int(amount)))
    return f"{sign}₹{text}"
