from django.db import migrations


def carry_over(apps, schema_editor):
    """Advances entered the old way — one monthly and one weekly figure per month —
    become an advance given on the 1st of that month, so every total stays the same."""
    Advance = apps.get_model("monitoring", "Advance")
    DayAdvance = apps.get_model("monitoring", "DayAdvance")
    for row in Advance.objects.all():
        amount = (row.monthly_advance or 0) + (row.weekly_advance or 0)
        if not amount:
            continue
        given, created = DayAdvance.objects.get_or_create(
            worker_id=row.worker_id, date=row.month, defaults={"amount": amount, "given_by_id": row.updated_by_id}
        )
        if not created:
            given.amount += amount
            given.save(update_fields=["amount"])


class Migration(migrations.Migration):
    dependencies = [
        ("monitoring", "0002_day_advances_and_complete_day"),
    ]

    operations = [
        migrations.RunPython(carry_over, migrations.RunPython.noop),
    ]
