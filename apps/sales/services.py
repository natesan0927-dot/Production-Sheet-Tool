"""
Business logic that must run regardless of which view/signal triggers it, so
the same rules always apply: generating the Customer Acquisition Form
automatically from data already stored in the CRM (never re-typed), per
spec section 17.
"""

from django.core.files.base import ContentFile

from apps.core.exports import render_pdf_response


def build_caf_context(order):
    customer = order.customer
    return {
        "order": order,
        "customer": customer,
        "quotation": order.quotation,
        "items": order.items.all(),
    }


def generate_customer_acquisition_form(order, user=None):
    from apps.sales.models import CustomerAcquisitionForm

    context = build_caf_context(order)
    exported = render_pdf_response(
        "sales/pdf/customer_acquisition_form.html", context,
        filename=f"CAF_{order.order_number}.pdf",
    )

    caf, created = CustomerAcquisitionForm.objects.get_or_create(order=order)
    if not created:
        caf.version += 1
    caf.generated_by = user
    caf.pdf_file.save(exported.filename, ContentFile(exported.content), save=False)
    caf.save()

    from apps.core.models import Document
    from django.contrib.contenttypes.models import ContentType

    doc = Document(
        content_type=ContentType.objects.get_for_model(order), object_id=order.pk,
        doc_type="Customer Acquisition Form", version=caf.version,
        uploaded_by=user, auto_generated=True, description="Auto-generated from CRM data",
    )
    doc.file.save(exported.filename, ContentFile(exported.content), save=True)

    order.status = "caf_generated"
    order.save(update_fields=["status"])

    from apps.core.notifications import notify_many
    from apps.accounts.models import User

    admin_staff = User.objects.filter(groups__name__in=["Admin Staff", "Super Admin"], is_active=True).distinct()
    notify_many(
        admin_staff, f"Customer Acquisition Form ready for {order.order_number}",
        url=order.get_absolute_url(), related_object=order,
    )
    return caf
