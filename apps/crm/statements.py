"""Printable statements for the accounts team.

Two documents: one customer's ledger, and everything still owed across the
business. Both are drawn here rather than stamped onto a template, because
neither exists on the client's stationery.

Amounts print as "Rs." and not the rupee sign: the built-in PDF fonts have no
glyph for U+20B9, so it would come out as a blank box on the printed page.
"""

from decimal import Decimal
from io import BytesIO

from django.http import HttpResponse
from django.utils.http import content_disposition_header
from django.utils import timezone
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import aging
from .templatetags.money import _group_indian

NAVY = colors.HexColor("#192265")
GOLD = colors.HexColor("#D4AF37")
INK = colors.HexColor("#1a1d29")
MUTED = colors.HexColor("#6b7280")
BAND = colors.HexColor("#f2f4f9")
ROSE = colors.HexColor("#b42318")

COMPANY = "TITANS WINDOWS"


def money(value, blank="—", prefix=True):
    """The app's own rupee grouping, in a form the PDF fonts can print.

    `prefix=False` drops the "Rs." for a table that says so in its own
    footnote — fifteen characters a cell is the difference between a column
    that fits and one that wraps mid-amount.
    """
    if value is None:
        return blank
    amount = Decimal(str(value)).quantize(Decimal("0.01"))
    sign = "-" if amount < 0 else ""
    whole, _, fraction = str(abs(amount)).partition(".")
    lead = "Rs. " if prefix else ""
    return f"{sign}{lead}{_group_indian(whole)}.{fraction or '00'}"


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontName="Helvetica-Bold", fontSize=15, textColor=NAVY, spaceAfter=2, alignment=0),
        "sub": ParagraphStyle("s", parent=base["Normal"], fontName="Helvetica", fontSize=9, textColor=MUTED),
        "cell": ParagraphStyle("c", parent=base["Normal"], fontName="Helvetica", fontSize=8.5, textColor=INK, leading=11),
        "cellr": ParagraphStyle("cr", parent=base["Normal"], fontName="Helvetica", fontSize=8.5, textColor=INK, leading=11, alignment=TA_RIGHT),
        "head": ParagraphStyle("h", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=8.5, textColor=colors.white, leading=11),
        "headr": ParagraphStyle("hr", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=8.5, textColor=colors.white, leading=11, alignment=TA_RIGHT),
        "note": ParagraphStyle("n", parent=base["Normal"], fontName="Helvetica", fontSize=8, textColor=MUTED),
    }


def _letterhead(canvas, doc):
    """The navy band and the gold rule, on every page."""
    canvas.saveState()
    width, height = A4
    canvas.setFillColor(NAVY)
    canvas.rect(0, height - 22 * mm, width, 22 * mm, stroke=0, fill=1)
    canvas.setFillColor(GOLD)
    canvas.rect(0, height - 23 * mm, width, 1 * mm, stroke=0, fill=1)

    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 15)
    canvas.drawString(18 * mm, height - 14 * mm, COMPANY)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GOLD)
    canvas.drawRightString(width - 18 * mm, height - 14 * mm, "Statement of Account")

    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(18 * mm, 12 * mm, f"Generated {timezone.localtime():%d %b %Y, %I:%M %p}")
    canvas.drawRightString(width - 18 * mm, 12 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _document(filename):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=30 * mm,
        bottomMargin=18 * mm,
        title=filename.rsplit(".", 1)[0],
        author=COMPANY,
    )
    return buffer, doc


def _respond(buffer, doc, story, filename, decorate=None):
    decorate = decorate or _letterhead
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    # A download, so a phone opens it in its own PDF app and the app stays where it was.
    # Spelled out for any alphabet: a Tamil name would otherwise reach the browser garbled.
    response["Content-Disposition"] = content_disposition_header(True, filename)
    return response


def _facts_table(pairs, style):
    """The small two-column block of details under the title."""
    rows = [[Paragraph(f"<b>{label}</b>", style["cell"]), Paragraph(escape(str(value)), style["cell"])] for label, value in pairs]
    table = Table(rows, colWidths=[38 * mm, 60 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _grid(data, widths, style, right_from=2, highlight_rows=(), pad=5):
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, GOLD),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (right_from, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), pad),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BAND]),
        ("LINEBELOW", (0, 1), (-1, -2), 0.25, colors.HexColor("#e2e6ef")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d7dbe6")),
    ]
    for index in highlight_rows:
        commands.append(("BACKGROUND", (0, index), (-1, index), colors.HexColor("#fff8e6")))
    table.setStyle(TableStyle(commands))
    return table


def render_customer_ledger(lead, rows):
    """One customer's account: every charge, every receipt, the balance."""
    style = _styles()
    story = [
        Paragraph(escape(lead.display_name), style["title"]),
        Paragraph(escape(lead.site_location), style["sub"]),
        Spacer(1, 7 * mm),
    ]

    facts = [("Quotation No.", lead.quotation_number or "—"), ("Invoice No.", lead.invoice_number or "—")]
    facts.append(("Invoice Date", f"{lead.invoice_date:%d %b %Y}" if lead.invoice_date else "Not invoiced"))
    facts.append(("Sales Executive", lead.assigned_to.display_name if lead.assigned_to else "—"))
    if lead.is_outstanding:
        facts.append(("Overdue By", f"{lead.overdue_days} days"))
    story += [_facts_table(facts, style), Spacer(1, 6 * mm)]

    data = [
        [
            Paragraph("Date", style["head"]),
            Paragraph("Particulars", style["head"]),
            Paragraph("Charged", style["headr"]),
            Paragraph("Received", style["headr"]),
            Paragraph("Balance", style["headr"]),
        ]
    ]
    highlight = []
    for row in rows:
        if row["kind"] == "charge":
            highlight.append(len(data))
        data.append(
            [
                Paragraph(f"{row['date']:%d %b %Y}" if row["date"] else "—", style["cell"]),
                Paragraph(escape(row["label"]), style["cell"]),
                Paragraph(money(row["charged"], blank=""), style["cellr"]),
                Paragraph(money(row["amount"], blank=""), style["cellr"]),
                Paragraph(money(row["balance"]), style["cellr"]),
            ]
        )
    story.append(_grid(data, [23 * mm, 70 * mm, 27 * mm, 27 * mm, 27 * mm], style, highlight_rows=highlight))
    story.append(Spacer(1, 6 * mm))

    totals = [
        ("Total billed", lead.invoice_total),
        ("Total received", lead.collected),
        ("Balance due", lead.balance_amount),
    ]
    summary = Table(
        [[Paragraph(f"<b>{label}</b>", style["cell"]), Paragraph(f"<b>{money(value)}</b>", style["cellr"])] for label, value in totals],
        colWidths=[47 * mm, 40 * mm],
        hAlign="RIGHT",
    )
    summary.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 0.8, NAVY),
                ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.HexColor("#d7dbe6")),
                ("TEXTCOLOR", (0, -1), (-1, -1), ROSE if (lead.balance_amount or 0) > 0 else NAVY),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(summary)

    if lead.extra_charges:
        story.append(Spacer(1, 4 * mm))
        story.append(
            Paragraph(
                f"Billed total includes {money(lead.extra_charges)} added to the invoice after the order was priced.",
                style["note"],
            )
        )

    filename = f"Ledger-{_filename(lead.customer_name)}.pdf"
    buffer, doc = _document(filename)
    return _respond(buffer, doc, story, filename)


def render_outstanding_statement(leads, range_key="all"):
    """Everything still owed, oldest debt first, with the totals underneath.

    `range_key` narrows it to invoices of a certain age. The whole list also
    carries an ageing summary; a single range does not, since it is one row of it.
    """
    style = _styles()
    range_key = aging.clean_key(range_key)
    everyone = list(leads)
    outstanding = sorted(
        aging.only_in_range(everyone, range_key),
        key=lambda lead: lead.overdue_days,
        reverse=True,
    )

    title = "Outstanding Statement"
    if range_key != "all":
        title += f" — overdue {aging.label(range_key).lower()}"
    story = [
        Paragraph(title, style["title"]),
        Paragraph("Invoiced orders with money still due, longest overdue first.", style["sub"]),
        Spacer(1, 7 * mm),
    ]

    data = [
        [
            Paragraph("#", style["head"]),
            Paragraph("Customer", style["head"]),
            Paragraph("Invoice", style["head"]),
            Paragraph("Invoiced", style["head"]),
            Paragraph("Billed", style["headr"]),
            Paragraph("Received", style["headr"]),
            Paragraph("Balance", style["headr"]),
            Paragraph("Overdue", style["headr"]),
        ]
    ]
    for index, lead in enumerate(outstanding, start=1):
        data.append(
            [
                Paragraph(str(index), style["cell"]),
                Paragraph(f"{escape(lead.display_name)}<br/><font color='#6b7280' size='7'>{escape(lead.site_location)}</font>", style["cell"]),
                Paragraph(escape(lead.invoice_number or "—"), style["cell"]),
                Paragraph(f"{lead.invoice_date:%d %b %y}" if lead.invoice_date else "—", style["cell"]),
                Paragraph(money(lead.invoice_total, prefix=False), style["cellr"]),
                Paragraph(money(lead.collected, prefix=False), style["cellr"]),
                Paragraph(f"<b>{money(lead.balance_amount, prefix=False)}</b>", style["cellr"]),
                Paragraph(str(lead.overdue_days), style["cellr"]),
            ]
        )

    if not outstanding:
        data.append([Paragraph("Nothing is outstanding.", style["cell"]), "", "", "", "", "", "", ""])

    widths = [7 * mm, 36 * mm, 24 * mm, 22 * mm, 22 * mm, 22 * mm, 22 * mm, 19 * mm]
    story.append(_grid(data, widths, style, right_from=4, pad=3))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("All amounts in rupees. Overdue counts days since the invoice date.", style["note"]))
    story.append(Spacer(1, 5 * mm))

    total_billed = sum((lead.invoice_total or Decimal("0")) for lead in outstanding)
    total_received = sum(lead.collected for lead in outstanding)
    total_due = sum((lead.balance_amount or Decimal("0")) for lead in outstanding)
    over_thirty = sum((lead.balance_amount or Decimal("0")) for lead in outstanding if lead.overdue_days > 30)

    rows = [
        ("Customers with money due", str(len(outstanding))),
        ("Total billed", money(total_billed)),
        ("Total received", money(total_received)),
        ("Total outstanding", money(total_due)),
        ("Of which overdue 30+ days", money(over_thirty)),
    ]
    summary = Table(
        [[Paragraph(f"<b>{label}</b>", style["cell"]), Paragraph(f"<b>{value}</b>", style["cellr"])] for label, value in rows],
        colWidths=[57 * mm, 40 * mm],
        hAlign="RIGHT",
    )
    summary.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 0.8, NAVY),
                ("LINEABOVE", (0, 3), (-1, 3), 0.5, colors.HexColor("#d7dbe6")),
                ("TEXTCOLOR", (0, 3), (-1, 3), ROSE),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(summary)

    if range_key == "all":
        story += [Spacer(1, 8 * mm), Paragraph("<b>Ageing summary</b>", style["cell"]), Spacer(1, 2 * mm)]
        rows = [[Paragraph("Overdue by", style["head"]), Paragraph("Customers", style["headr"]), Paragraph("Amount due", style["headr"])]]
        for name, count, amount in aging.by_band(everyone):
            rows.append([Paragraph(name, style["cell"]), Paragraph(str(count), style["cellr"]), Paragraph(money(amount), style["cellr"])])
        story.append(_grid(rows, [50 * mm, 30 * mm, 45 * mm], style, right_from=1))

    suffix = "" if range_key == "all" else f"-{range_key}-days"
    filename = f"Outstanding{suffix}-{timezone.localdate():%Y-%m-%d}.pdf"
    buffer, doc = _document(filename)
    return _respond(buffer, doc, story, filename)


def _filename(name):
    from .scan import name_character

    cleaned = "".join(character if name_character(character) else "-" for character in name)
    return "-".join(part for part in cleaned.split("-") if part) or "customer"
