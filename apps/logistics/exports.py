from apps.core.exports import ExportedFile, register_pdf, render_pdf_response, timestamp_suffix


@register_pdf("dispatch")
def export_dispatch(dispatch):
    return render_pdf_response(
        "logistics/pdf/dispatch_challan.html", {"dispatch": dispatch, "order": dispatch.order},
        filename=f"DispatchChallan_{dispatch.dispatch_id}_{timestamp_suffix()}.pdf",
    )


@register_pdf("installation")
def export_installation(installation):
    handover = getattr(installation, "handover", None)
    if handover and handover.certificate_pdf:
        handover.certificate_pdf.open("rb")
        content = handover.certificate_pdf.read()
        handover.certificate_pdf.close()
        return ExportedFile(
            filename=f"Handover_{installation.order.order_number}.pdf", content=content, content_type="application/pdf"
        )
    return render_pdf_response(
        "logistics/pdf/installation_summary.html", {"installation": installation, "order": installation.order},
        filename=f"Installation_{installation.installation_id}_{timestamp_suffix()}.pdf",
    )
