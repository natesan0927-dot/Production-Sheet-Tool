"""
PDF / Excel generation, plus the registry that powers the automatic
"local copy" download: whenever an employee saves one of the major business
records, their browser immediately downloads a PDF or Excel copy of it to
their own machine (see apps.core.mixins.AutoLocalExportMixin), and a second
copy is written to DOCUMENT_BACKUP_ROOT on the server as a safety net.

Register a model with:

    from apps.core.exports import register_pdf, register_excel

    @register_pdf("quotation")
    def export_quotation(obj):
        return render_pdf_response("sales/pdf/quotation.html", {"quotation": obj},
                                    filename=f"{obj.quotation_number}.pdf")

    @register_excel("measurementrequest")
    def export_measurement(obj):
        rows = [...]
        return workbook_response(["Window", "Width", "Height"], rows,
                                  filename=f"{obj.measurement_id}.xlsx")
"""

import io
from datetime import datetime

from django.template.loader import render_to_string
from openpyxl import Workbook
from openpyxl.styles import Font
from xhtml2pdf import pisa

# model class -> (kind, callable(obj) -> ExportedFile)
_REGISTRY = {}


class ExportedFile:
    def __init__(self, filename, content: bytes, content_type: str):
        self.filename = filename
        self.content = content
        self.content_type = content_type


def _register(model_lookup_name, kind):
    def decorator(func):
        _REGISTRY[model_lookup_name.lower()] = (kind, func)
        return func

    return decorator


def register_pdf(model_lookup_name):
    return _register(model_lookup_name, "pdf")


def register_excel(model_lookup_name):
    return _register(model_lookup_name, "excel")


def get_exporter(model_name: str):
    """model_name is the Django ContentType 'model' string, e.g. 'quotation'."""
    return _REGISTRY.get(model_name.lower())


def is_registered(model_name: str) -> bool:
    return model_name.lower() in _REGISTRY


def _html_to_pdf_bytes(html: str) -> bytes:
    buffer = io.BytesIO()
    pisa.CreatePDF(src=html, dest=buffer, encoding="utf-8")
    return buffer.getvalue()


def _pdf_base_context():
    """
    Shared context every generated PDF's letterhead needs. Logo comes from
    the static source tree (via staticfiles finders), not CompanyProfile.logo
    -- the latter is a media upload, and this host's media storage isn't
    reliably persistent (see TESTING_DEPLOYMENT.md), whereas the bundled
    static file always exists in the checked-out source. xhtml2pdf needs a
    real filesystem path here, not a URL.
    """
    from django.contrib.staticfiles import finders

    from apps.core.models import CompanyProfile

    return {"company": CompanyProfile.load(), "logo_path": finders.find("branding/titans_logo.png")}


def render_pdf_response(template_name, context, filename) -> ExportedFile:
    """Render a PDF from a template *file* (the usual case)."""
    full_context = _pdf_base_context()
    full_context.update(context)
    html = render_to_string(template_name, full_context)
    return ExportedFile(filename=filename, content=_html_to_pdf_bytes(html), content_type="application/pdf")


def render_pdf_response_from_string(html_body, context, filename) -> ExportedFile:
    """
    Render a PDF from a template *string* -- used for the admin-editable
    DocumentTemplate.html_body, so an admin can tweak a document's layout
    without touching code. Same context/company injection as
    render_pdf_response, just a Django Template string instead of a file.
    """
    from django.template import Context, Template

    full_context = _pdf_base_context()
    full_context.update(context)
    html = Template(html_body).render(Context(full_context))
    return ExportedFile(filename=filename, content=_html_to_pdf_bytes(html), content_type="application/pdf")


def workbook_response(headers, rows, filename, sheet_title="Data") -> ExportedFile:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title[:31]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append(row)
    for column_cells in ws.columns:
        length = max((len(str(c.value)) if c.value is not None else 0) for c in column_cells)
        ws.column_dimensions[column_cells[0].column_letter].width = min(max(length + 2, 10), 60)

    buffer = io.BytesIO()
    wb.save(buffer)
    return ExportedFile(
        filename=filename,
        content=buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def as_download_response(exported: "ExportedFile"):
    from django.http import HttpResponse

    response = HttpResponse(exported.content, content_type=exported.content_type)
    response["Content-Disposition"] = f'attachment; filename="{exported.filename}"'
    return response


def timestamp_suffix():
    return datetime.now().strftime("%Y%m%d_%H%M%S")
