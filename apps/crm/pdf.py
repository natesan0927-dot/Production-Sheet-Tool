"""The documents the business hands to a customer.

All three are the client's own PDFs, kept in documents/ and filled in — we never
redraw their stationery. The warranty certificate is the customer's to keep; the
handover & work completion certificate is the one they sign, and it comes back
as the proof of handover.

Fill positions are (x, distance down from the top of the page), taken from the
printed label each value sits beside. The templates have a mediabox that does
not start at y=0, so the conversion to PDF user space uses the page's own box.
"""

from io import BytesIO

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.utils.http import content_disposition_header
from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .scan import name_character

DOCUMENTS = settings.BASE_DIR / "documents"
CAF_TEMPLATE = DOCUMENTS / "caf_template.pdf"
WARRANTY_TEMPLATE = DOCUMENTS / "warranty_template.pdf"
HANDOVER_TEMPLATE = DOCUMENTS / "handover_template.pdf"

FONT = "Helvetica-Bold"
INK = (0.05, 0.05, 0.15)
# Sit just above the printed rule rather than straight on it.
BASELINE_LIFT = 2

# The handover certificate is set in Calibri Bold. Carlito is its open twin — the
# same width for every letter — so what is filled in reads as the certificate's
# own printing and lines up with it. (Calibri itself cannot ship with the app.)
CALIBRI_TWIN = "Carlito-Bold"
CALIBRI_TWIN_FILE = DOCUMENTS / "fonts" / "Carlito-Bold.ttf"


def _calibri_twin():
    if CALIBRI_TWIN not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(CALIBRI_TWIN, str(CALIBRI_TWIN_FILE)))
    return CALIBRI_TWIN


def _slug(name):
    """A customer's name, safe to hand a browser as a download filename."""
    cleaned = "".join(character if name_character(character) else "-" for character in name)
    return "-".join(part for part in cleaned.split("-") if part) or "lead"


def field(x, y_from_top, text, size=11, align="left", max_width=None, font=FONT, char_space=0.0,
          lift=BASELINE_LIFT, ink=INK, run_to=None, line_end=None):
    """One value to print on a template.

    `max_width` is the blank it should fit, shrinking if need be. Or, for a blank
    that is a run of underscores ending at `line_end`: the value keeps its size,
    the printed line is carried on underneath anything longer, as far as `run_to`
    (an x on the page), and only past that is the value made smaller.
    """
    return {"x": x, "y": y_from_top, "text": text, "size": size, "align": align, "max_width": max_width,
            "font": font, "char_space": char_space, "lift": lift, "ink": ink, "run_to": run_to,
            "line_end": line_end}


def _width(text, font, size, char_space=0.0):
    return stringWidth(text, font, size) + char_space * len(text)


def _fitted(item):
    """The text and size to print: within the blank if it can be, readable either way."""
    text, font, size, spacing = str(item["text"]), item["font"], item["size"], item["char_space"]
    if item["run_to"] is not None:
        room = item["run_to"] - item["x"]
        while size > 8 and _width(text, font, size, spacing) > room:
            size -= 0.25
        while len(text) > 1 and _width(text, font, size, spacing) > room:
            text = text[:-2].rstrip() + "…"
        return text, size
    blank = item["max_width"]
    while blank and size > 6 and _width(text, font, size, spacing) > blank:
        size -= 0.5
    return text, size


def _carry_line_on(overlay, item, x, y, text_end):
    """More of the printed underscores, under a value longer than its blank.

    Drawn with the underscore itself — the same letter, size and spacing the
    template uses — so the longer line is indistinguishable from the printed one.
    It starts one underscore back, over the end of the printed line, so there is
    no seam.
    """
    font, size, spacing = item["font"], item["size"], item["char_space"]
    step = _width("_", font, size, spacing)
    start = item["line_end"] - step
    count = 1
    while start + count * step < text_end + BLANK_INSET:
        count += 1
    line = overlay.beginText(start, y)
    line.setFont(font, size)
    line.setCharSpace(spacing)
    line.setFillColorRGB(*item["ink"])
    line.textOut("_" * count)
    overlay.drawText(line)


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
            for item in values:
                text, size = _fitted(item)
                y = top - item["y"] + item["lift"]
                x = item["x"]
                if item["align"] == "center":
                    x -= _width(text, item["font"], size, item["char_space"]) / 2
                line = overlay.beginText(x, y)
                line.setFont(item["font"], size)
                line.setCharSpace(item["char_space"])
                line.setFillColorRGB(*item["ink"])
                line.textOut(text)
                overlay.drawText(line)
                end = x + _width(text, item["font"], size, item["char_space"])
                if item["line_end"] is not None and end + BLANK_INSET > item["line_end"]:
                    _carry_line_on(overlay, item, x, y, end)
            overlay.save()
            buffer.seek(0)
            page.merge_page(PdfReader(buffer).pages[0])
        writer.add_page(page)

    return _as_pdf(writer, filename)


def _as_pdf(writer, filename):
    output = BytesIO()
    writer.write(output)
    response = HttpResponse(output.getvalue(), content_type="application/pdf")
    # A download, so a phone opens it in its own PDF app and the app stays where it was.
    # Spelled out for any alphabet: a Tamil name would otherwise reach the browser garbled.
    response["Content-Disposition"] = content_disposition_header(True, filename)
    return response


def render_caf(lead):
    """Order Confirmation — quotation block on page 1, client name on page 2.

    The date sits in a printed ____/____/________ rule, so each part is centred
    over its own group of underscores.
    """
    quotation_date = timezone.localtime(lead.quotation_uploaded_at).strftime("%d / %m / %Y") if lead.quotation_uploaded_at else ""
    issued = timezone.localtime(lead.won_at or lead.updated_at)
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


# Where the handover certificate's blanks are, measured off the client's PDF:
# (start of the printed line, its end, the label's baseline down from the top).
# Page 1 is set at 14.79 pt with 0.13 pt between letters; page 2 at 13.515 pt,
# spaced 1 pt. A value is printed in the same size and spacing, on the label's
# own baseline, starting just inside the line; a longer value has the line carried
# on underneath it.
HANDOVER_PAGE_1 = {"size": 14.79, "char_space": 0.13}
HANDOVER_PAGE_2 = {"size": 13.515, "char_space": 1.0}
HANDOVER_BLANKS = {
    "date": (0, 70.50, 236.00, 260.46),
    "site": (0, 220.00, 385.50, 296.46),
    "customer": (0, 142.00, 307.50, 332.46),
    "quotation": (0, 197.00, 362.50, 368.46),
    "ack_customer": (1, 142.50, 405.00, 390.42),
    "ack_mobile": (1, 140.50, 403.50, 480.42),
}
# Just inside the start of the line, and never past the page's right-hand margin.
BLANK_INSET = 3
RIGHT_MARGIN = 590


def _handover_field(blank, text):
    page, start, end, baseline = HANDOVER_BLANKS[blank]
    style = HANDOVER_PAGE_1 if page == 0 else HANDOVER_PAGE_2
    return page, field(
        start + BLANK_INSET,
        baseline,
        text,
        style["size"],
        font=_calibri_twin(),
        char_space=style["char_space"],
        lift=0,
        ink=(0, 0, 0),
        run_to=RIGHT_MARGIN,
        line_end=end,
    )


def render_handover_certificate(lead):
    """The handover & work completion certificate, on the client's own stationery.

    Filled from the job: the date, the project and site, the customer and the
    quotation on the first page; the customer's name and mobile in their
    acknowledgement. Signatures, the signing dates and anything only the
    customer can give are left for the site. Dated the day it was handed over
    once that is on record, otherwise the day it is printed.
    """
    handed_over = timezone.localtime(lead.handover_signed_at).date() if lead.handover_signed_at else timezone.localdate()
    pages = {}
    for blank, text in [
        ("date", handed_over.strftime("%d/%m/%Y")),
        ("site", lead.project_label),
        ("customer", lead.display_name),
        ("quotation", lead.quotation_number),
        ("ack_customer", lead.display_name),
        ("ack_mobile", f"+91 {lead.phone}" if lead.phone else ""),
    ]:
        page, item = _handover_field(blank, text)
        pages.setdefault(page, []).append(item)
    return _stamp(HANDOVER_TEMPLATE, pages, f"Handover-{_slug(lead.customer_name)}.pdf")
