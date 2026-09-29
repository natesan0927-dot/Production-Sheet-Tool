"""What is already stored, carried over to 0018's new shape.

  * every payment's single proof becomes its first receipt (the file itself does
    not move);
  * a job already handed over was plainly installed, so it is marked installed on
    the day of its handover; one dispatched and not yet handed over waits for
    someone to mark it, like any new one;
  * an installer charge already agreed keeps its amount, and its rate per sq ft is
    worked out from it where the site's sq ft is known.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations
from django.utils import timezone


def carry_over(apps, schema_editor):
    Lead = apps.get_model("crm", "Lead")
    Payment = apps.get_model("crm", "Payment")
    InstallerPayment = apps.get_model("crm", "InstallerPayment")
    PaymentReceipt = apps.get_model("crm", "PaymentReceipt")
    InstallerReceipt = apps.get_model("crm", "InstallerReceipt")

    for payment in Payment.objects.exclude(file=""):
        PaymentReceipt.objects.create(payment=payment, file=payment.file.name)
    for payment in InstallerPayment.objects.exclude(file=""):
        InstallerReceipt.objects.create(payment=payment, file=payment.file.name)

    for lead in Lead.objects.filter(dispatched_at__isnull=False, installation_completed_on__isnull=True).exclude(
        handover_signed_at__isnull=True, completed_at__isnull=True
    ):
        when = lead.handover_signed_at or lead.completed_at
        Lead.objects.filter(pk=lead.pk).update(
            installation_completed_on=timezone.localtime(when).date(),
            installation_completed_at=when,
            installation_completed_by_id=lead.handover_signed_by_id or lead.completed_by_id,
        )

    for lead in Lead.objects.filter(installation_charge__isnull=False, installation_rate__isnull=True, total_sqft__gt=0):
        rate = (lead.installation_charge / lead.total_sqft).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        Lead.objects.filter(pk=lead.pk).update(installation_rate=rate)


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0018_installation_step_and_receipts"),
    ]

    operations = [
        migrations.RunPython(carry_over, migrations.RunPython.noop),
    ]
