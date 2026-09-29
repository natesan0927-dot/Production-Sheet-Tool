from datetime import timedelta

from django.db import migrations
from django.db.models import F
from django.utils import timezone


def clear_old_completions(apps, schema_editor):
    """To-dos finished before "Assigned by me" existed.

    Whoever handed them out was told at the time, so a column full of old
    completions would only be something to clear by hand. The last week's stay,
    so recent news is not lost.
    """
    Task = apps.get_model("crm", "Task")
    week_ago = timezone.now() - timedelta(days=7)
    Task.objects.filter(done=True, done_at__lt=week_ago).update(cleared_by_assigner_at=F("done_at"))
    Task.objects.filter(done=True, done_at__isnull=True).update(cleared_by_assigner_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0021_installer_payable_and_todo_status"),
    ]

    operations = [
        migrations.RunPython(clear_old_completions, migrations.RunPython.noop),
    ]
