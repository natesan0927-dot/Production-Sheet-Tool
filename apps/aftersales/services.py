from dateutil.relativedelta import relativedelta
from django.core.files.base import ContentFile
from django.utils import timezone

from apps.core.exports import render_pdf_response
from apps.core.models import CompanyProfile


def activate_warranty(order, user=None):
    from apps.aftersales.models import Warranty

    if hasattr(order, "warranty"):
        return order.warranty

    company = CompanyProfile.load()
    start = timezone.now().date()
    end = start + relativedelta(years=company.default_warranty_years or 10)

    warranty = Warranty.objects.create(
        order=order,
        product_summary=", ".join(f"{i.description} x{i.quantity}" for i in order.items.all()),
        warranty_start_date=start,
        warranty_end_date=end,
        warranty_terms=company.default_warranty_terms,
    )

    exported = render_pdf_response(
        "aftersales/pdf/warranty_certificate.html", {"warranty": warranty, "order": order},
        filename=f"Warranty_{warranty.certificate_number}.pdf",
    )
    warranty.certificate_pdf.save(exported.filename, ContentFile(exported.content), save=True)

    order.status = "completed"
    order.save(update_fields=["status"])

    from apps.core.notifications import notify

    if order.salesperson:
        notify(order.salesperson, f"Warranty activated for {order.order_number}", url=warranty.get_absolute_url(), related_object=warranty)

    return warranty
