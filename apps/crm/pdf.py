"""The documents the business hands to a customer.

The CAF and the warranty certificate are the client's own PDFs, kept in
documents/ and filled in — we never redraw their stationery. The handover
certificate has no supplied original, so it is drawn here in the same navy and
gold, and can be swapped for a real template later.

Fill positions are (x, distance down from the top of the page), taken from the
printed label each value sits beside. Both templates have a mediabox that does
not start at y=0, so the conversion to PDF user space uses the page's own box.
"""

from io import BytesIO

from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import HttpResponse
from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

DOCUMENTS = settings.BASE_DIR / "documents"
CAF_TEMPLATE = DOCUMENTS / "caf_template.pdf"
WARRANTY_TEMPLATE = DOCUMENTS / "warranty_template.pdf"

FONT = "Helvetica-Bold"
BODY = "Helvetica"
NAVY = HexColor("#0B1A3A")
GOLD = HexColor("#D9AF3E")
INK = HexColor("#0D0D26")
# Sit just above the printed rule rather than straight on it.
BASELINE_LIFT = 2


def field(x, y_from_top, text, size=11, align="left", max_width=None):
    return {"x": x, "y": y_from_top, "text": text, "size": size, "align": align, "max_width": max_width}


def _fitted_size(text, size, max_width):
    """Shrink a value that would otherwise run past the end of its blank."""
    while max_width and size > 6 and stringWidth(str(text), FONT, size) > max_width:
        size -= 0.5
    return size


def _stamp(template, page_values, filename):
    reader = PdfReader(template)
    writer = PdfWriter()

    for index, page in enumerate(reader.pages):
        values = [item for item in page_values.get(index, []) if item["text"]]
        if values:
            box = page.mediabox
            top, right = float(box.top), float(box.right)
            buffer = BytesIO()
            overlay = canvas.Canvas(buffer, pagesize=(right, top))
            overlay.setFillColor(INK)
            for item in values:
                text = str(item["text"])
                size = _fitted_size(text, item["size"], item["max_width"])
                overlay.setFont(FONT, size)
                y = top - item["y"] + BASELINE_LIFT
                if item["align"] == "center":
                    overlay.drawCentredString(item["x"], y, text)
                else:
                    overlay.drawString(item["x"], y, text)
            overlay.save()
            buffer.seek(0)
            page.merge_page(PdfReader(buffer).pages[0])
        writer.add_page(page)

    return _as_pdf(writer, filename)


def _as_pdf(writer, filename):
    output = BytesIO()
    writer.write(output)
    response = HttpResponse(output.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


def render_caf(lead):
    """Order Confirmation — quotation block on page 1, client name on page 2.

    The date sits in a printed ____/____/________ rule, so each part is centred
    over its own group of underscores.
    """
    quotation_date = lead.quotation_uploaded_at.strftime("%d / %m / %Y") if lead.quotation_uploaded_at else ""
    issued = lead.won_at or lead.updated_at
    date_line = 187.25
    return _stamp(
        CAF_TEMPLATE,
        {
            0: [
                field(514, date_line, issued.strftime("%d"), 10.5, align="center"),
                field(544, date_line, issued.strftime("%m"), 10.5, align="center"),
                field(585, date_line, issued.strftime("%Y"), 10.5, align="center"),
                field(320, 414.50, lead.quotation_number, 11, max_width=128),
                field(293, 447.50, quotation_date, 11, max_width=150),
                field(332, 480.50, lead.project_label, 11, max_width=120),
            ],
            1: [field(88, 656.23, lead.customer_name, 11, max_width=330)],
        },
        f"CAF-{lead.lead_number}.pdf",
    )


def render_warranty_certificate(lead):
    invoice_date = lead.invoice_date.strftime("%d / %m / %Y") if lead.invoice_date else ""
    return _stamp(
        WARRANTY_TEMPLATE,
        {
            0: [
                field(204, 251.56, lead.customer_name, 10, max_width=170),
                field(252, 268.55, lead.invoice_number, 10, max_width=120),
                field(251, 283.52, invoice_date, 10, max_width=120),
            ],
        },
        f"Warranty-{lead.lead_number}.pdf",
    )


def render_handover_certificate(lead):
    """Drawn here — the client supplied no original for this one."""
    width, height = A4
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)

    # --- letterhead ---------------------------------------------------------
    pdf.setFillColor(NAVY)
    pdf.rect(0, height - 108, width, 108, stroke=0, fill=1)
    logo = finders.find("branding/titans_logo.png")
    if logo:
        pdf.drawImage(ImageReader(logo), 40, height - 96, width=72, height=72, mask="auto")
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont(FONT, 24)
    pdf.drawString(128, height - 52, "TITANS WINDOWS")
    pdf.setFont(BODY, 8.5)
    for offset, line in enumerate(
        [
            "100/2 Mangadu Main Road, Malayambakkam, Poonamallee, Chennai 600 056",
            "Contact: +91 8778623728   ·   sales@titansupvcwindows.com   ·   GSTIN: 33CBZPN0233Q1Z0",
        ]
    ):
        pdf.drawString(128, height - 70 - offset * 12, line)

    # --- title --------------------------------------------------------------
    pdf.setFillColor(NAVY)
    pdf.setFont(FONT, 17)
    pdf.drawCentredString(width / 2, height - 152, "HANDOVER CERTIFICATE")
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(2)
    pdf.line(width / 2 - 110, height - 160, width / 2 + 110, height - 160)

    pdf.setFillColor(INK)
    pdf.setFont(BODY, 10.5)
    pdf.drawCentredString(
        width / 2,
        height - 186,
        "This is to certify that the work described below has been completed and handed over to the customer.",
    )

    # --- details ------------------------------------------------------------
    rows = [
        ("Customer Name", lead.customer_name),
        ("Contact Number", lead.phone),
        ("Project / Site Location", lead.project_label),
        ("Quotation Reference No.", lead.quotation_number or "—"),
        ("Invoice Number", lead.invoice_number or "—"),
        ("Date of Invoice", lead.invoice_date.strftime("%d / %m / %Y") if lead.invoice_date else "—"),
        ("Number of Windows", str(lead.window_count) if lead.window_count else "—"),
        ("Total Site Area (sq ft)", str(lead.total_sqft) if lead.total_sqft else "—"),
        ("Installed By", lead.installation_person or "—"),
        ("Date of Handover", (lead.dispatched_at or lead.updated_at).strftime("%d / %m / %Y")),
    ]
    y = height - 226
    for label, value in rows:
        pdf.setFillColor(NAVY)
        pdf.setFont(FONT, 10)
        pdf.drawString(60, y, f"{label}")
        pdf.setFillColor(INK)
        pdf.setFont(BODY, 10)
        pdf.drawString(240, y, str(value))
        pdf.setStrokeColor(HexColor("#E5E7F0"))
        pdf.setLineWidth(0.6)
        pdf.line(60, y - 7, width - 60, y - 7)
        y -= 26

    # --- declaration and signatures ----------------------------------------
    pdf.setFillColor(INK)
    pdf.setFont(BODY, 10)
    y -= 18
    for line in [
        "I confirm that the above work has been completed as per the approved quotation, that the",
        "installation has been inspected, and that the site has been handed over in good condition.",
    ]:
        pdf.drawString(60, y, line)
        y -= 16

    y -= 46
    pdf.setStrokeColor(INK)
    pdf.setLineWidth(0.8)
    pdf.line(60, y, 250, y)
    pdf.line(width - 250, y, width - 60, y)
    pdf.setFont(FONT, 9.5)
    pdf.drawString(60, y - 14, "Customer Signature & Date")
    pdf.drawString(width - 250, y - 14, "For TITANS WINDOWS")
    pdf.setFont(BODY, 9)
    pdf.drawString(60, y - 30, lead.customer_name)

    # --- footer band --------------------------------------------------------
    pdf.setFillColor(NAVY)
    pdf.rect(0, 0, width, 26, stroke=0, fill=1)
    pdf.setFillColor(GOLD)
    pdf.setFont(BODY, 8)
    pdf.drawCentredString(width / 2, 10, f"{lead.lead_number}  ·  Titans Windows  ·  Premium uPVC Windows & Doors")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    writer = PdfWriter()
    writer.append(PdfReader(buffer))
    return _as_pdf(writer, f"Handover-{lead.lead_number}.pdf")
