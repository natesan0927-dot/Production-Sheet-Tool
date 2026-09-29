from datetime import timedelta

from django.db import migrations
from django.db.models import F


def forget_refused_texts(apps, schema_editor):
    """OTPs for proving a number that the SMS service refused to send.

    They used to be stored and then retired in the same moment, and still
    counted towards three an hour, so failed attempts could lock the Super
    Admin out of trying again. Nothing was texted, so nothing is lost.
    """
    PasswordResetCode = apps.get_model("accounts", "PasswordResetCode")
    PasswordResetCode.objects.filter(
        purpose="verify",
        tries=0,
        used_at__isnull=False,
        used_at__lte=F("created_at") + timedelta(seconds=15),
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_mobile_otp"),
    ]

    operations = [
        migrations.RunPython(forget_refused_texts, migrations.RunPython.noop),
    ]
