from apps.core.exports import ExportedFile, register_pdf, render_pdf_response, timestamp_suffix


@register_pdf("warranty")
def export_warranty(warranty):
    if warranty.certificate_pdf:
        warranty.certificate_pdf.open("rb")
        content = warranty.certificate_pdf.read()
        warranty.certificate_pdf.close()
        return ExportedFile(filename=f"Warranty_{warranty.certificate_number}.pdf", content=content, content_type="application/pdf")
    return render_pdf_response(
        "aftersales/pdf/warranty_certificate.html", {"warranty": warranty, "order": warranty.order},
        filename=f"Warranty_{warranty.certificate_number}.pdf",
    )


@register_pdf("servicecomplaint")
def export_complaint(complaint):
    return render_pdf_response(
        "aftersales/pdf/service_complaint.html", {"complaint": complaint},
        filename=f"Complaint_{complaint.complaint_number}_{timestamp_suffix()}.pdf",
    )
