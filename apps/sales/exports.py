from apps.core.exports import ExportedFile, register_pdf, render_pdf_response, timestamp_suffix


@register_pdf("quotation")
def export_quotation(quotation):
    return render_pdf_response(
        "sales/pdf/quotation.html", {"quotation": quotation, "items": quotation.items.all()},
        filename=f"{quotation.quotation_number}_{timestamp_suffix()}.pdf",
    )


@register_pdf("order")
def export_order(order):
    return render_pdf_response(
        "sales/pdf/order_confirmation.html", {"order": order, "items": order.items.all()},
        filename=f"{order.order_number}_Confirmation_{timestamp_suffix()}.pdf",
    )


@register_pdf("customeracquisitionform")
def export_caf(caf):
    if caf.pdf_file:
        caf.pdf_file.open("rb")
        content = caf.pdf_file.read()
        caf.pdf_file.close()
        return ExportedFile(filename=f"CAF_{caf.order.order_number}_v{caf.version}.pdf", content=content, content_type="application/pdf")
    from apps.sales.services import build_caf_context

    return render_pdf_response(
        "sales/pdf/customer_acquisition_form.html", build_caf_context(caf.order),
        filename=f"CAF_{caf.order.order_number}_v{caf.version}.pdf",
    )
