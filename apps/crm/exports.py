from apps.core.exports import register_excel, register_pdf, render_pdf_response, timestamp_suffix, workbook_response


@register_pdf("customer")
def export_customer(customer):
    return render_pdf_response(
        "crm/pdf/customer_profile.html",
        {"customer": customer},
        filename=f"Customer_{customer.customer_code}_{timestamp_suffix()}.pdf",
    )


@register_pdf("lead")
def export_lead(lead):
    return render_pdf_response(
        "crm/pdf/lead_summary.html",
        {"lead": lead},
        filename=f"Lead_{lead.lead_id}_{timestamp_suffix()}.pdf",
    )


@register_excel("followup")
def export_followup(followup):
    headers = ["Lead", "Type", "Date", "Discussion", "Customer Response", "Next Action", "Next Follow-up"]
    rows = [[
        followup.lead.lead_id, followup.get_type_display(), str(followup.date),
        followup.discussion, followup.customer_response, followup.next_action,
        str(followup.next_followup_date or ""),
    ]]
    return workbook_response(headers, rows, filename=f"FollowUp_{followup.lead.lead_id}_{timestamp_suffix()}.xlsx")
