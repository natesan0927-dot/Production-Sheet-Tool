"""Fills the client's own certificate PDFs.

The two files in documents/ are the originals supplied by the client. We never
redraw them — we stamp the lead's details onto the blank lines, so what the
customer signs is exactly the company's own stationery.

Positions are given as (x, distance down from the top of the page), measured
from the printed label each value sits beside. Both templates have a mediabox
that does not start at y=0, so the conversion to PDF user space uses the page's
own box rather than its height.
"""

from io import BytesIO

from django.conf import settings
from django.http import HttpResponse
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

DOCUMENTS = settings.BASE_DIR / "documents"
CAF_TEMPLATE = DOCUMENTS / "caf_template.pdf"
WARRANTY_TEMPLATE = DOCUMENTS / "warranty_template.pdf"

FONT = "Helvetica-Bold"
# Sit just above the printed rule rather than straight on it.
BASELINE_LIFT = 2


def _stamp(template, page_values, filename):
    """page_values maps a page index to [(x, y_from_top, text, size), ...]."""
    reader = PdfReader(template)
    writer = PdfWriter()

    for index, page in enumerate(reader.pages):
        values = [item for item in page_values.get(index, []) if item[2]]
        if values:
            box = page.mediabox
            top, right = float(box.top), float(box.right)
            buffer = BytesIO()
            overlay = canvas.Canvas(buffer, pagesize=(right, top))
            overlay.setFillColorRGB(0.05, 0.05, 0.15)
            for x, y_from_top, text, size in values:
                overlay.setFont(FONT, size)
                overlay.drawString(x, top - y_from_top + BASELINE_LIFT, str(text))
            overlay.save()
            buffer.seek(0)
            page.merge_page(PdfReader(buffer).pages[0])
        writer.add_page(page)

    output = BytesIO()
    writer.write(output)
    response = HttpResponse(output.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


def render_caf(lead):
    """Order Confirmation — the quotation block on page 1, the client name on page 2."""
    quotation_date = lead.quotation_uploaded_at.strftime("%d / %m / %Y") if lead.quotation_uploaded_at else ""
    issued = lead.won_at or lead.updated_at
    return _stamp(
        CAF_TEMPLATE,
        {
            0: [
                (505, 187.25, issued.strftime("%d / %m / %Y"), 11),
                (320, 414.50, lead.quotation_number, 11),
                (293, 447.50, quotation_date, 11),
                (332, 480.50, lead.site_location, 11),
            ],
            1: [
                (88, 656.23, lead.customer_name, 11),
            ],
        },
        f"CAF-{lead.lead_number}.pdf",
    )


def render_warranty_certificate(lead):
    invoice_date = lead.invoice_date.strftime("%d / %m / %Y") if lead.invoice_date else ""
    return _stamp(
        WARRANTY_TEMPLATE,
        {
            0: [
                (204, 251.56, lead.customer_name, 10),
                (252, 268.55, lead.invoice_number, 10),
                (251, 283.52, invoice_date, 10),
            ],
        },
        f"Warranty-{lead.lead_number}.pdf",
    )
