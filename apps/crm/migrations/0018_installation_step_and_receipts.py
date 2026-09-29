"""Installation becomes a step of its own, the installer is paid by the sq ft, and a
payment can carry several proofs. The new columns and tables only; what is
already stored is carried over in 0019, and the old proof column goes in 0020 —
Postgres will not index a table in the same transaction that just updated it.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0017_updates_clear_themselves'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='lead',
            name='installation_completed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='lead',
            name='installation_completed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='lead',
            name='installation_completed_on',
            field=models.DateField(blank=True, null=True, verbose_name='Installation completed on'),
        ),
        migrations.AddField(
            model_name='lead',
            name='installation_rate',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Installation rate per sq ft'),
        ),
        migrations.AddField(
            model_name='lead',
            name='installation_reminded_on',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='lead',
            name='installation_charge',
            field=models.DecimalField(blank=True, decimal_places=2, help_text="What the installer is paid for this site: the rate times the site's sq ft.", max_digits=12, null=True, verbose_name='Installation charge'),
        ),
        migrations.CreateModel(
            name='InstallerReceipt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to='installers/%Y/%m/', verbose_name='Proof / receipt')),
                ('payment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='receipts', to='crm.installerpayment')),
            ],
            options={
                'ordering': ['id'],
            },
        ),
        migrations.CreateModel(
            name='PaymentReceipt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to='payments/%Y/%m/', verbose_name='Proof / receipt')),
                ('payment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='receipts', to='crm.payment')),
            ],
            options={
                'ordering': ['id'],
            },
        ),
    ]
