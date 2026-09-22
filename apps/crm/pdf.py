"""Server-side PDF generation for the two documents the client supplied:
the Order Confirmation (CAF) and the hardware warranty certificate.
"""

from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from xhtml2pdf import pisa


def _link_callback(uri, rel):
    """Resolve /static/... and /media/... URLs to real files for xhtml2pdf."""
    for prefix, root in ((settings.STATIC_URL, None), (settings.MEDIA_URL, settings.MEDIA_ROOT)):
        prefix = prefix if prefix.startswith("/") else f"/{prefix}"
        if uri.startswith(prefix):
            relative = uri[len(prefix):]
            if root is None:
                found = finders.find(relative)
                if found:
                    return found
            else:
                candidate = Path(root) / relative
                if candidate.exists():
                    return str(candidate)
    return uri


def _pdf_response(template, context, filename):
    html = render_to_string(template, context)
    buffer = BytesIO()
    result = pisa.CreatePDF(html, dest=buffer, link_callback=_link_callback, encoding="utf-8")
    if result.err:
        return HttpResponse("Could not generate the PDF.", status=500)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def render_caf(lead):
    context = {
        "lead": lead,
        "today": timezone.localdate(),
        "quotation_date": lead.quotation_uploaded_at,
    }
    return _pdf_response("pdf/caf.html", context, f"CAF-{lead.lead_number}.pdf")


def render_warranty_certificate(lead):
    return _pdf_response(
        "pdf/warranty_certificate.html",
        {"lead": lead},
        f"Warranty-{lead.lead_number}.pdf",
    )
