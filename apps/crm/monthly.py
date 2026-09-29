"""The month in numbers: what was sold, billed, collected, and what to do about it.

Every figure here is worked out from the records, never typed in, so the report
can be opened for any month — the current one while it is still running, or a
closed one to compare against.

Two decisions worth knowing before reading the numbers:

* **Who took an order.** The person who marked it won, falling back to whoever
  owns the lead. A lead that has since been reassigned still credits the person
  who actually closed it.
* **What "outstanding" means for a past month.** The ledger keeps dates, so the
  amount due *at the end of that month* is worked out properly from the payments
  and charges dated before then, and shown next to what is still due today.

Amounts are Decimals throughout; percentages are rounded only for display.
"""

from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from . import aging
from .models import (
    FollowUp,
    InstallerPayment,
    InvoiceCharge,
    Lead,
    MarketingSpend,
    Payment,
    SalesTarget,
    ServiceComplaint,
)
from .templatetags.money import rupees_short

ZERO = Decimal("0")
TREND_MONTHS = 6
SOURCE_LABELS = dict(Lead.LEAD_SOURCES)


# ---------------------------------------------------------------- calendar
def month_start(value):
    return value.replace(day=1)


def next_month(first):
    return date(first.year + (first.month == 12), first.month % 12 + 1, 1)


def previous_month(first):
    return date(first.year - (first.month == 1), (first.month - 2) % 12 + 1, 1)


def months_back(first, count):
    """`count` months ending at `first`, oldest first."""
    months = [first]
    for _ in range(count - 1):
        months.append(previous_month(months[-1]))
    return list(reversed(months))


def _aware(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def last_day(first):
    return date(first.year, first.month, monthrange(first.year, first.month)[1])


def parse_month(text, today=None):
    """"2026-09" -> the 1st of that month; anything else, or the future, -> this month.

    Nothing earlier than the first month with any leads in it: there is nothing to
    report there, and walking back far enough reaches years the calendar refuses.
    """
    today = today or timezone.localdate()
    try:
        year, month = (int(part) for part in (text or "").split("-"))
        chosen = date(year, month, 1)
    except (ValueError, TypeError):
        return month_start(today)
    return max(min(chosen, month_start(today)), first_month_with_data(today))


def first_month_with_data(today=None):
    earliest = Lead.objects.order_by("created_at").values_list("created_at", flat=True).first()
    today = today or timezone.localdate()
    return month_start(timezone.localtime(earliest).date()) if earliest else month_start(today)


# ---------------------------------------------------------------- money helpers
def _charges(lead):
    return sum((c.amount for c in lead.invoice_charges.all()), ZERO)


def _received(lead):
    return (lead.advance_received or ZERO) + sum((p.amount for p in lead.payments.all()), ZERO)


def _billed(lead):
    return (lead.order_value or ZERO) + _charges(lead)


def _balance(lead):
    return _billed(lead) - _received(lead)


def _due_at(lead, cutoff_day):
    """What the customer owed on the morning of `cutoff_day`, from dated entries only."""
    charges = sum((c.amount for c in lead.invoice_charges.all() if timezone.localtime(c.added_at).date() < cutoff_day), ZERO)
    advance = (lead.advance_received or ZERO) if lead.won_at and timezone.localtime(lead.won_at).date() < cutoff_day else ZERO
    paid = sum((p.amount for p in lead.payments.all() if p.paid_on < cutoff_day), ZERO)
    return max(ZERO, (lead.order_value or ZERO) + charges - advance - paid)


def _percent(part, whole):
    return None if not whole else float(part) * 100 / float(whole)


def _change(now, before):
    """Percent change, or None when there was nothing to compare with."""
    if not before:
        return None
    return (float(now) - float(before)) * 100 / float(before)


def _lakhs(value):
    return round(float(value) / 100000, 2)


def _average(numbers):
    """The mean of the numbers there are; a step with a missing date is left out, not counted as zero."""
    numbers = [number for number in numbers if number is not None]
    return round(sum(numbers) / len(numbers), 1) if numbers else None


def _days_between(start, end):
    if not start or not end:
        return None
    return max(0, (end - start).days)


def taker(lead):
    """Who an order counts for — the same rule as the Sales Target page (models.credited_q)."""
    return lead.credited_to


# ---------------------------------------------------------------- one month's headline figures
def _orders_between(start, end):
    return list(
        Lead.objects.filter(status=Lead.Status.WON, won_at__gte=start, won_at__lt=end)
        .select_related("won_by", "assigned_to")
        .prefetch_related("invoice_charges", "payments")
    )


def _headline(first):
    """The four numbers the trend is built from, for one month."""
    nxt = next_month(first)
    start, end = _aware(first), _aware(nxt)
    orders = _orders_between(start, end)
    invoiced = list(
        Lead.objects.filter(status=Lead.Status.WON, invoice_date__gte=first, invoice_date__lt=nxt).prefetch_related(
            "invoice_charges", "payments"
        )
    )
    posted = Payment.objects.filter(paid_on__gte=first, paid_on__lt=nxt).aggregate(t=Sum("amount"))["t"] or ZERO
    advances = sum((lead.advance_received or ZERO for lead in orders), ZERO)
    return {
        "first": first,
        "label": first.strftime("%b %y"),
        "orders_count": len(orders),
        "orders_value": sum((lead.order_value or ZERO for lead in orders), ZERO),
        "invoiced_value": sum((_billed(lead) for lead in invoiced), ZERO),
        "collected": posted + advances,
    }


# ---------------------------------------------------------------- the report
def report(first, today=None):
    today = today or timezone.localdate()
    nxt = next_month(first)
    start, end = _aware(first), _aware(nxt)
    closing = last_day(first)
    is_current = first == month_start(today)
    prior = previous_month(first)

    orders = _orders_between(start, end)
    order_value = sum((lead.order_value or ZERO for lead in orders), ZERO)
    created = list(Lead.objects.filter(created_at__gte=start, created_at__lt=end))
    lost = list(Lead.objects.filter(status=Lead.Status.LOST, lost_at__gte=start, lost_at__lt=end).select_related("assigned_to"))
    decided = len(orders) + len(lost)
    earliest = first_month_with_data(today)

    headline = _headline(first)
    last_month = _headline(prior)
    trend = [_headline(m) for m in months_back(first, TREND_MONTHS)]
    same_month_last_year = _headline(date(first.year - 1, first.month, 1))

    # ---- billing and money owed -------------------------------------------------
    invoiced = list(
        Lead.objects.filter(status=Lead.Status.WON, invoice_date__gte=first, invoice_date__lt=nxt)
        .select_related("assigned_to")
        .prefetch_related("invoice_charges", "payments")
    )
    invoiced_value = sum((_billed(lead) for lead in invoiced), ZERO)
    due_at_month_end = sum((_due_at(lead, nxt) for lead in invoiced), ZERO)
    due_today = sum((max(ZERO, _balance(lead)) for lead in invoiced), ZERO)

    every_invoice = list(
        Lead.objects.filter(status=Lead.Status.WON, invoice_date__isnull=False)
        .select_related("assigned_to")
        .prefetch_related("invoice_charges", "payments")
    )
    owing = [(lead, _balance(lead), (today - lead.invoice_date).days) for lead in every_invoice if _balance(lead) > 0]
    outstanding_now = sum((amount for _, amount, _ in owing), ZERO)
    bands = []
    for name, low, high in aging.BANDS:
        inside = [amount for _, amount, days in owing if days >= low and (high is None or days <= high)]
        bands.append({"label": name, "count": len(inside), "amount": sum(inside, ZERO)})
    debtors = sorted(owing, key=lambda row: -row[1])[:5]
    over_thirty = bands[2]["amount"]

    extras = InvoiceCharge.objects.filter(added_at__gte=start, added_at__lt=end).aggregate(t=Sum("amount"))["t"] or ZERO
    advances = sum((lead.advance_received or ZERO for lead in orders), ZERO)
    posted = Payment.objects.filter(paid_on__gte=first, paid_on__lt=nxt).aggregate(t=Sum("amount"))["t"] or ZERO
    collected = posted + advances

    # How much of this month's invoices has been paid: by the month's end for a
    # closed month, so far for the running one. (What came in during the month also
    # pays older invoices, so it is not compared with this month's billing.)
    still_due = due_today if is_current else due_at_month_end
    paid_share = _percent(invoiced_value - still_due, invoiced_value)

    # ---- sales executives ------------------------------------------------------
    from apps.accounts.models import User

    targets = {t.salesperson_id: t.amount for t in SalesTarget.objects.filter(month=first)}
    people = {}

    def person(user):
        return people.setdefault(
            user.pk,
            {"user": user, "orders": 0, "value": ZERO, "created": 0, "lost": 0, "overdue": 0, "target": targets.get(user.pk)},
        )

    for lead in orders:
        row = person(taker(lead))
        row["orders"] += 1
        row["value"] += lead.order_value or ZERO
    for lead in created:
        person(lead.assigned_to)["created"] += 1
    for lead in lost:
        person(lead.assigned_to)["lost"] += 1
    overdue_by_person = defaultdict(int)
    for followup in FollowUp.objects.filter(done=False, date__lt=today, lead__status=Lead.Status.OPEN).select_related("lead"):
        overdue_by_person[followup.lead.assigned_to_id] += 1
    for user_id, count in overdue_by_person.items():
        if user_id in people:
            people[user_id]["overdue"] = count
    for user_id, count in overdue_by_person.items():
        if user_id not in people:
            person(User.objects.get(pk=user_id))["overdue"] = count
    # Someone with a target and nothing to show yet is exactly who needs seeing.
    for user in User.objects.filter(pk__in=[pk for pk in targets if pk not in people]):
        person(user)
    executives = sorted(people.values(), key=lambda row: (-row["value"], row["user"].display_name.lower()))
    for row in executives:
        row["share"] = _percent(row["value"], order_value)
        row["average"] = (row["value"] / row["orders"]) if row["orders"] else None
        row["reached"] = _percent(row["value"], row["target"]) if row["target"] else None
        row["conversion"] = _percent(row["orders"], row["orders"] + row["lost"]) if (row["orders"] + row["lost"]) else None
    total_target = sum((t for t in targets.values()), ZERO)

    # ---- lead sources -------------------------------------------------------------
    spend = {s.source: s.amount for s in MarketingSpend.objects.filter(month=first)}
    sources = []
    for key, label in Lead.LEAD_SOURCES:
        got = [lead for lead in created if lead.lead_source == key]
        won = [lead for lead in orders if lead.lead_source == key]
        gone = [lead for lead in lost if lead.lead_source == key]
        value = sum((lead.order_value or ZERO for lead in won), ZERO)
        outlay = spend.get(key)
        sources.append(
            {
                "key": key,
                "label": label,
                "leads": len(got),
                "orders": len(won),
                "lost": len(gone),
                "value": value,
                "share": _percent(value, order_value),
                "average": (value / len(won)) if won else None,
                "conversion": _percent(len(won), len(won) + len(gone)) if (won or gone) else None,
                "spend": outlay,
                "per_lead": (outlay / len(got)) if outlay and got else None,
                "per_order": (outlay / len(won)) if outlay and won else None,
                "return": (float(value) / float(outlay)) if outlay and value else (0.0 if outlay else None),
            }
        )
    sources = [row for row in sources if row["leads"] or row["orders"] or row["lost"] or row["spend"]]
    sources.sort(key=lambda row: (-row["value"], -row["leads"]))
    total_spend = sum((s for s in spend.values()), ZERO)

    # ---- speed and operations -----------------------------------------------------
    cycle = _average(_days_between(lead.created_at, lead.won_at) for lead in orders)
    dispatched = list(Lead.objects.filter(dispatched_at__gte=start, dispatched_at__lt=end))
    production_time = _average(_days_between(lead.won_at, lead.dispatched_at) for lead in dispatched)
    quoted = list(Lead.objects.filter(quotation_uploaded_at__gte=start, quotation_uploaded_at__lt=end, measurement_done_at__isnull=False))
    quotation_time = _average(_days_between(lead.measurement_done_at, lead.quotation_uploaded_at) for lead in quoted)
    completed = Lead.objects.filter(completed_at__gte=start, completed_at__lt=end).count()

    complaints_raised = ServiceComplaint.objects.filter(raised_at__gte=start, raised_at__lt=end).count()
    complaints_resolved = ServiceComplaint.objects.filter(resolved_at__gte=start, resolved_at__lt=end).count()
    complaints_open = ServiceComplaint.objects.filter(resolved_at__isnull=True).count()

    installer_paid = InstallerPayment.objects.filter(paid_on__gte=first, paid_on__lt=nxt).aggregate(t=Sum("amount"))["t"] or ZERO
    installer_owed = ZERO
    for lead in Lead.objects.filter(status=Lead.Status.WON, dispatched_at__isnull=False, installation_charge__isnull=False).prefetch_related("installer_payments"):
        installer_owed += max(ZERO, lead.installation_charge - sum((p.amount for p in lead.installer_payments.all()), ZERO))

    followups_made = FollowUp.objects.filter(created_at__gte=start, created_at__lt=end).count()
    followups_worked = FollowUp.objects.filter(
        done_at__gte=start, done_at__lt=end, superseded=False, closed_with_lead=False
    ).count()
    followups_rescheduled = FollowUp.objects.filter(done_at__gte=start, done_at__lt=end, superseded=True).count()
    overdue_now = sum(overdue_by_person.values())

    # ---- lost ------------------------------------------------------------------------
    lost_value = sum((lead.expected_value or ZERO for lead in lost), ZERO)
    beaten_on_price = [lead for lead in lost if lead.lost_price_elsewhere and lead.expected_value and lead.lost_price_elsewhere < lead.expected_value]
    biggest_losses = sorted(lost, key=lambda lead: -(lead.expected_value or ZERO))[:8]

    open_leads = Lead.objects.filter(status=Lead.Status.OPEN)
    pipeline_value = open_leads.aggregate(t=Sum("expected_value"))["t"] or ZERO

    data = {
        "first": first,
        "last": closing,
        "title": first.strftime("%B %Y"),
        "is_current": is_current,
        "is_final": today > closing,
        "days_left": max(0, (closing - today).days) if is_current else 0,
        "previous": prior if prior >= earliest else None,
        "following": nxt if nxt <= month_start(today) else None,
        "headline": {
            "orders_count": len(orders),
            "orders_value": order_value,
            "orders_average": (order_value / len(orders)) if orders else None,
            "invoiced_count": len(invoiced),
            "invoiced_value": invoiced_value,
            "due_at_month_end": due_at_month_end,
            "due_today": due_today,
            "collected": collected,
            "paid_share": paid_share,
            "still_due": still_due,
            "leads_created": len(created),
            "lost_count": len(lost),
            "win_rate": _percent(len(orders), decided),
            "extras": extras,
            "change_orders": _change(order_value, last_month["orders_value"]),
            "change_invoiced": _change(invoiced_value, last_month["invoiced_value"]),
            "change_collected": _change(collected, last_month["collected"]),
            "against_last_month": last_month,
            "against_last_year": same_month_last_year,
            "change_year": _change(order_value, same_month_last_year["orders_value"]),
        },
        "executives": executives,
        "total_target": total_target,
        "team_reached": _percent(order_value, total_target) if total_target else None,
        "trend": trend,
        "sources": sources,
        "total_spend": total_spend,
        "receivables": {"total": outstanding_now, "bands": bands, "debtors": debtors, "over_thirty": over_thirty},
        "speed": {"cycle": cycle, "production": production_time, "quotation": quotation_time},
        "operations": {
            "dispatched": len(dispatched),
            "dispatched_sqft": sum((lead.total_sqft or ZERO for lead in dispatched), ZERO),
            "completed": completed,
            "complaints_raised": complaints_raised,
            "complaints_resolved": complaints_resolved,
            "complaints_open": complaints_open,
            "installer_paid": installer_paid,
            "installer_owed": installer_owed,
            "followups_made": followups_made,
            "followups_worked": followups_worked,
            "followups_rescheduled": followups_rescheduled,
            "overdue_now": overdue_now,
        },
        "lost": {
            "count": len(lost),
            "value": lost_value,
            "on_price": len(beaten_on_price),
            "biggest": biggest_losses,
            "pipeline_value": pipeline_value,
            "open_count": open_leads.count(),
        },
    }
    data["insights"] = insights(data)
    data["charts"] = chart_data(data)
    return data


# ---------------------------------------------------------------- what stands out
def insights(d):
    """Plain sentences, each true of the numbers above, in order of how much they matter.

    Money first (what came in, what is stuck), then where the leads came from and what
    was wasted, then the people and the pace. If a month somehow has more to say than
    fits, the pace notes at the end are the ones to go.
    """
    said = []
    h = d["headline"]
    month = d["first"].strftime("%B")
    last = h["against_last_month"]["first"].strftime("%B")

    def add(tone, icon, text):
        said.append({"tone": tone, "icon": icon, "text": text})

    # --- what was sold
    if h["orders_count"] == 0:
        add("warn", "fa-circle-exclamation", f"No order has been confirmed in {month} yet.")
    else:
        text = f"{h['orders_count']} order{'s' if h['orders_count'] != 1 else ''} worth {rupees_short(h['orders_value'])} taken in {month}"
        if h["change_orders"] is not None:
            direction = "up" if h["change_orders"] >= 0 else "down"
            text += f", {direction} {abs(h['change_orders']):.0f}% on {last} ({rupees_short(h['against_last_month']['orders_value'])})"
        up = (h["change_orders"] or 0) >= 0
        add("good" if up else "warn", "fa-arrow-trend-up" if up else "fa-arrow-trend-down", text + ".")
    if d["team_reached"] is not None:
        add("good" if d["team_reached"] >= 100 else "info", "fa-bullseye", f"The team reached {d['team_reached']:.0f}% of its combined target ({rupees_short(d['total_target'])}).")

    # --- where it came from, and where money went for nothing
    winners = [row for row in d["sources"] if row["value"] > 0]
    if winners:
        best = winners[0]
        add("good", "fa-trophy", f"{best['label']} brought the most business: {rupees_short(best['value'])} from {best['orders']} order{'s' if best['orders'] != 1 else ''} ({best['share']:.0f}% of the month).")
    dead = [row for row in d["sources"] if row["leads"] >= 3 and row["orders"] == 0]
    if dead:
        worst = max(dead, key=lambda row: row["leads"])
        cost = f", and {rupees_short(worst['spend'])} was spent on it" if worst["spend"] else ""
        add("warn", "fa-magnifying-glass-minus", f"{worst['label']} brought {worst['leads']} leads and no orders{cost}.")
    priced = [row for row in d["sources"] if row["spend"] and row["orders"]]
    if len(priced) >= 2:
        efficient = max(priced, key=lambda row: row["return"])
        add("info", "fa-coins", f"{efficient['label']} returned the most for its spend: ₹{efficient['return']:.1f} of orders for every ₹1.")

    # --- money stuck
    if h["paid_share"] is not None and h["invoiced_value"]:
        if h["paid_share"] < 70:
            add("warn", "fa-hand-holding-dollar", f"Only {h['paid_share']:.0f}% of what was invoiced in {month} ({rupees_short(h['invoiced_value'])}) has been paid. {rupees_short(h['still_due'])} of it is still due.")
        else:
            add("good", "fa-hand-holding-dollar", f"{h['paid_share']:.0f}% of what was invoiced in {month} has been paid.")
    if d["receivables"]["over_thirty"] > 0:
        add("warn", "fa-hourglass-half", f"{rupees_short(d['receivables']['over_thirty'])} has been unpaid for over 30 days, out of {rupees_short(d['receivables']['total'])} outstanding in all.")

    # --- what got away
    if d["lost"]["count"]:
        text = f"{d['lost']['count']} lead{'s' if d['lost']['count'] != 1 else ''} worth {rupees_short(d['lost']['value'])} were lost"
        if d["lost"]["on_price"]:
            text += f"; {d['lost']['on_price']} went to a lower price elsewhere"
        add("warn", "fa-circle-xmark", text + ".")

    # --- people and pace
    late = max(d["executives"], key=lambda row: row["overdue"], default=None)
    if late and late["overdue"] >= 2:
        add("warn", "fa-bell", f"{late['user'].display_name} has {late['overdue']} overdue follow-ups, the most on the team.")
    if d["speed"]["quotation"] is not None and d["speed"]["quotation"] >= 3:
        add("warn", "fa-file-invoice", f"Quotations took {d['speed']['quotation']:g} days on average after measurement — the slowest step you control.")
    ranked = [row for row in d["executives"] if row["orders"]]
    if len(ranked) >= 2:
        add("info", "fa-user-tie", f"{ranked[0]['user'].display_name} closed the most ({rupees_short(ranked[0]['value'])}); {ranked[-1]['user'].display_name} closed {rupees_short(ranked[-1]['value'])}.")
    if d["speed"]["cycle"] is not None:
        add("info", "fa-clock", f"An order took {d['speed']['cycle']:g} days on average from first enquiry to confirmation.")
    return said[:12]


# ---------------------------------------------------------------- the charts
def chart_data(d):
    return {
        "executives": {
            "labels": [row["user"].display_name for row in d["executives"] if row["value"] or row["target"]],
            "values": [_lakhs(row["value"]) for row in d["executives"] if row["value"] or row["target"]],
            "targets": [_lakhs(row["target"]) if row["target"] else None for row in d["executives"] if row["value"] or row["target"]],
        },
        "trend": {
            "labels": [month["label"] for month in d["trend"]],
            "orders": [_lakhs(month["orders_value"]) for month in d["trend"]],
            "invoiced": [_lakhs(month["invoiced_value"]) for month in d["trend"]],
            "collected": [_lakhs(month["collected"]) for month in d["trend"]],
        },
        "sources": {
            "labels": [row["label"] for row in d["sources"] if row["value"] > 0],
            "values": [_lakhs(row["value"]) for row in d["sources"] if row["value"] > 0],
        },
        "aging": {
            "labels": [band["label"] for band in d["receivables"]["bands"]],
            "values": [_lakhs(band["amount"]) for band in d["receivables"]["bands"]],
        },
    }


# ---------------------------------------------------------------- saving what was spent
def save_spend(first, posted):
    """Store the amounts typed against each source; blank clears one. Returns how many are set."""
    kept = 0
    for key, _ in Lead.LEAD_SOURCES:
        text = (posted.get(f"spend_{key}") or "").replace(",", "").strip()
        if not text:
            MarketingSpend.objects.filter(month=first, source=key).delete()
            continue
        try:
            amount = Decimal(text)
        except Exception:
            continue
        if amount < 0:
            continue
        MarketingSpend.objects.update_or_create(month=first, source=key, defaults={"amount": amount})
        kept += 1
    return kept


def is_last_day(today=None):
    today = today or timezone.localdate()
    return today == last_day(month_start(today))
