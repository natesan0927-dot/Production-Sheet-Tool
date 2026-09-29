"""The single proof column on payments, now that every proof is a receipt (0019)."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0019_carry_over_installation_and_proofs"),
    ]

    operations = [
        migrations.RemoveField(
            model_name='installerpayment',
            name='file',
        ),
        migrations.RemoveField(
            model_name='payment',
            name='file',
        ),
    ]
