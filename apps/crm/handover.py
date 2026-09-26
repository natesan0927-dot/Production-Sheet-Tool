"""The handover certificate.

The warranty certificate and the CAF are the client's own printed stationery,
so those are filled in by stamping values onto the PDF. There is no printed
handover form, so this one is drawn: the same navy-and-gold letterhead, the
job's details filled in from the record, and the signature lines left blank
for the site.

Amounts and the crest follow the statements module, so a customer handed both
documents on the same day sees one house style.
"""

from django.contrib.staticfiles import finders
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle

from .statements import BAND, COMPANY, GOLD, INK, MUTED, NAVY, _document, _respond

DECLARATION = (
    "This is to certify that the uPVC windows and doors supplied by {company} against the "
    "details above have been installed at the site and handed over to the customer. The "
    "customer has inspected the installation and confirms that the work is complete, that "
    "the material and workmanship are in good order, and that the site has been left clean."
)

NOTE = (
    "The warranty certificate issued alongside this document remains with the customer. "
    "A signed copy of this certificate is retained by {company} as the record of handover."
)


def _crest():
    """The logo, if collectstatic has put it where we can find it."""
    path = finders.find("branding/titans_logo.png")
    if not path:
        return None
    try:
        return Image(path, width=18 * mm, height=18 * mm, kind="proportional")
    except Exception:
        # A certificate without its crest still does its job; a 500 does not.
        return None


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontName="Helvetica-Bold", fontSize=17, textColor=NAVY, alignment=1, spaceAfter=1),
        "kicker": ParagraphStyle("k", parent=base["Normal"], fontName="Helvetica", fontSize=8.5, textColor=GOLD, alignment=1),
        "body": ParagraphStyle("b", parent=base["Normal"], fontName="Helvetica", fontSize=9.5, textColor=INK, leading=15, spaceAfter=5),
        "label": ParagraphStyle("l", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9, textColor=NAVY, leading=13),
        "value": ParagraphStyle("v", parent=base["Normal"], fontName="Helvetica", fontSize=9.5, textColor=INK, leading=13),
        "sign": ParagraphStyle("s", parent=base["Normal"], fontName="Helvetica", fontSize=8.5, textColor=MUTED, leading=12),
        "note": ParagraphStyle("n", parent=base["Normal"], fontName="Helvetica-Oblique", fontSize=8, textColor=MUTED, leading=11),
    }


def _frame(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setFillColor(NAVY)
    canvas.rect(0, height - 24 * mm, width, 24 * mm, stroke=0, fill=1)
    canvas.setFillColor(GOLD)
    canvas.rect(0, height - 25 * mm, width, 1 * mm, stroke=0, fill=1)

    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 16)
    canvas.drawString(18 * mm, height - 15 * mm, COMPANY)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GOLD)
    canvas.drawRightString(width - 18 * mm, height - 15 * mm, "uPVC Windows & Doors")

    # A thin gold rule above the footer, to close the page off.
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(0.7)
    canvas.line(18 * mm, 15 * mm, width - 18 * mm, 15 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(18 * mm, 10 * mm, "Handover Certificate")
    canvas.drawRightString(width - 18 * mm, 10 * mm, COMPANY)
    canvas.restoreState()


def _details(lead, style):
    """Every blank the office would otherwise fill in by hand."""
    pairs = [
        ("Customer Name", lead.customer_name),
        ("Contact Number", lead.phone),
        ("Project / Site", lead.project_label),
        ("Invoice Number", lead.invoice_number or "—"),
        ("Invoice Date", f"{lead.invoice_date:%d %b %Y}" if lead.invoice_date else "—"),
        ("Number of Windows", str(lead.window_count) if lead.window_count else "—"),
        ("Total Area (sq ft)", f"{lead.total_sqft:,.2f}" if lead.total_sqft else "—"),
        ("Date of Dispatch", f"{lead.dispatched_at:%d %b %Y}" if lead.dispatched_at else "—"),
        ("Installed By", lead.installation_person or "—"),
    ]
    rows = [[Paragraph(label, style["label"]), Paragraph(str(value), style["value"])] for label, value in pairs]
    table = Table(rows, colWidths=[45 * mm, 129 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, BAND]),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d7dbe6")),
                ("LINEBEFORE", (0, 0), (0, -1), 2, GOLD),
            ]
        )
    )
    return table


def _signatures(style):
    """Left blank on purpose — these are signed on site."""
    blank = "_" * 34

    def block(who, lines):
        rows = [[Paragraph(f"<b>{who}</b>", style["label"])]]
        rows += [[Paragraph(f"{blank}<br/><font size='7.5'>{line}</font>", style["sign"])] for line in lines]
        inner = Table(rows, colWidths=[80 * mm])
        inner.setStyle(
            TableStyle(
                [
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ]
            )
        )
        return inner

    outer = Table(
        [[block("Customer", ["Name", "Signature", "Date"]), block(f"For {COMPANY}", ["Name", "Authorised Signatory", "Date"])]],
        colWidths=[87 * mm, 87 * mm],
        hAlign="LEFT",
    )
    outer.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    return outer


def build_handover(lead, filename):
    style = _styles()
    story = []

    crest = _crest()
    if crest:
        crest.hAlign = "CENTER"
        story += [crest, Spacer(1, 3 * mm)]

    story += [
        Paragraph("HANDOVER CERTIFICATE", style["title"]),
        Paragraph("Confirmation of installation and site handover", style["kicker"]),
        Spacer(1, 8 * mm),
        _details(lead, style),
        Spacer(1, 7 * mm),
        Paragraph(DECLARATION.format(company=COMPANY), style["body"]),
        Spacer(1, 9 * mm),
        _signatures(style),
        Spacer(1, 8 * mm),
        Paragraph(NOTE.format(company=COMPANY), style["note"]),
    ]

    buffer, doc = _document(filename)
    doc.topMargin = 32 * mm
    doc.bottomMargin = 20 * mm
    return _respond(buffer, doc, story, filename, decorate=_frame)

