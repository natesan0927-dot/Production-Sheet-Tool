"""The documents the business hands to a customer.

Both are the client's own PDFs, kept in documents/ and filled in — we never
redraw their stationery. The handover certificate is the client's guarantee
certificate: the customer signs it and it comes back as the proof of handover.

Fill positions are (x, distance down from the top of the page), taken from the
printed label each value sits beside. Both templates have a mediabox that does
not start at y=0, so the conversion to PDF user space uses the page's own box.
"""

from io import BytesIO

from django.conf import settings
from django.http import HttpResponse
from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

DOCUMENTS = settings.BASE_DIR / "documents"
CAF_TEMPLATE = DOCUMENTS / "caf_template.pdf"
WARRANTY_TEMPLATE = DOCUMENTS / "warranty_template.pdf"

FONT = "Helvetica-Bold"
INK = (0.05, 0.05, 0.15)
# Sit just above the printed rule rather than straight on it.
BASELINE_LIFT = 2


def _slug(name):
    """A customer's name, safe to hand a browser as a download filename."""
    cleaned = "".join(character if character.isalnum() else "-" for character in name)
    return "-".join(part for part in cleaned.split("-") if part) or "lead"


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
            overlay.setFillColorRGB(*INK)
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
        f"CAF-{_slug(lead.customer_name)}.pdf",
    )


def render_warranty_certificate(lead):
    """The client's own guarantee certificate. The customer keeps this one."""
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
        f"Warranty-{_slug(lead.customer_name)}.pdf",
    )


def render_handover_certificate(lead):
    """The certificate the customer signs to say the job is finished.

    Drawn rather than stamped: unlike the warranty and the CAF there is no
    printed stationery for it, so the letterhead is reproduced here. Every
    blank the office would otherwise fill in by hand is filled from the job,
    and only the signatures are left empty.
    """
    from .handover import build_handover

    return build_handover(lead, f"Handover-{_slug(lead.customer_name)}.pdf")
