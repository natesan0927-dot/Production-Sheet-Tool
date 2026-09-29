"""Updates that clear themselves, and follow-ups that close with their lead.

Adds the fields, then tidies what is already in the database the way the new code
would have: every update gets the topic and link it would be sent with today, and
those whose work has since been done are cleared (off "Updates for the day" and
out of the bell's count; they stay in the Notifications list). Follow-ups still
open on a lead that was won or lost are closed with it, as the new code does.
Nothing is deleted.
"""

import re
from datetime import date, timedelta

from django.db import migrations, models
from django.utils import timezone

LEAD_PREFIXES = [
    ("Rough measurement needed", "rough"),
    ("Measurements ready for quotation", "quotation"),
    ("Quotation needs revision", "quotation"),
    ("Rough measurement completed for", "quotation"),
    ("Revised quotation", "decision"),
    ("CAF & final measurement pending", "caf"),
    ("Final measurement ready", "sheet"),
    ("Production sheet needs revision", "sheet"),
    ("Production sheet awaiting your approval", "approval"),
    ("Production sheet approved", "floor"),
    ("Dispatched — warranty & handover pending", "handover"),
]
QUOTATION_SENT = re.compile(r"^Quotation .+ uploaded for ")
PASSWORD = re.compile(r"\(([^()]+)\) has forgotten their password")
ASSIGNED = re.compile(r"^.+? assigned you: (.+)$")
MONTH = re.compile(r"^Summary for the Month — (\w+) (\d{4}) is ready")
MONTHS = {name: number for number, name in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], start=1)}


def lead_topic(message):
    for prefix, topic in LEAD_PREFIXES:
        if message.startswith(prefix):
            return topic
    return "decision" if QUOTATION_SENT.match(message) else ""


def settled(lead, topic):
    """Whether what an update of this kind asked for has since been done."""
    if lead.status == "lost":
        return True
    if topic == "rough":
        return lead.measurement_done_at is not None
    if topic == "quotation":
        return lead.quotation_uploaded_at is not None and not lead.quotation_revision_pending
    if topic == "decision":
        return lead.status != "open" or lead.quotation_revision_pending
    if topic == "caf":
        return lead.caf_signed_at is not None and lead.final_measurement_at is not None
    if topic == "sheet":
        return lead.production_approved_at is not None or (
            lead.production_sheet_at is not None and lead.production_revision_at is None
        )
    if topic == "approval":
        return lead.production_approved_at is not None or lead.production_revision_at is not None
    if topic == "floor":
        return lead.dispatched_at is not None
    if topic == "handover":
        return lead.completed_at is not None
    return False


def mark_replaced(apps):
    """Quotations and elevation reports a revision superseded, going by when they came in.

    From now on a revision marks them as it goes; for what is already stored, a
    file that arrived well before the latest quotation was stamped is an earlier one.
    """
    Lead = apps.get_model("crm", "Lead")
    LeadFile = apps.get_model("crm", "LeadFile")
    for lead in Lead.objects.filter(quotation_uploaded_at__isnull=False):
        cutoff = lead.quotation_uploaded_at - timedelta(minutes=5)
        LeadFile.objects.filter(lead=lead, kind="quotation", uploaded_at__lt=cutoff).update(
            replaced_at=lead.quotation_uploaded_at
        )
        elevations = list(LeadFile.objects.filter(lead=lead, kind="elevation").order_by("-uploaded_at", "-pk"))
        for older in elevations[1:]:
            LeadFile.objects.filter(pk=older.pk).update(replaced_at=elevations[0].uploaded_at)


def tidy(apps, schema_editor):
    mark_replaced(apps)
    Notification = apps.get_model("crm", "Notification")
    FollowUp = apps.get_model("crm", "FollowUp")
    Task = apps.get_model("crm", "Task")
    ServiceComplaint = apps.get_model("crm", "ServiceComplaint")
    User = apps.get_model("accounts", "User")
    PasswordRequest = apps.get_model("accounts", "PasswordRequest")
    now = timezone.now()

    FollowUp.objects.filter(done=False).exclude(lead__status="open").update(
        done=True, done_at=now, closed_with_lead=True
    )

    for note in Notification.objects.filter(topic="").select_related("lead"):
        message = note.message
        topic, link, done = "", "", False

        if note.lead_id:
            lead = note.lead
            topic = lead_topic(message)
            if topic:
                done = settled(lead, topic)
            elif message.startswith("Service complaint raised"):
                complaint = (
                    ServiceComplaint.objects.filter(lead=lead, raised_at__lte=note.created_at + timedelta(minutes=1))
                    .order_by("-raised_at")
                    .first()
                )
                link = "/service-requests/"
                if complaint:
                    topic = f"complaint:{complaint.pk}"
                    done = complaint.resolved_at is not None
            elif message.startswith(("Service complaint resolved", "Project completed")):
                link = f"/completed/?q={lead.lead_number}"
        else:
            password = PASSWORD.search(message)
            assigned = ASSIGNED.match(message)
            month = MONTH.match(message)
            if password:
                person = User.objects.filter(username=password.group(1)).first()
                link = "/accounts/employees/#password-requests"
                if person:
                    topic = f"password:{person.pk}"
                    done = not PasswordRequest.objects.filter(user=person, handled_at__isnull=True).exists()
            elif month and month.group(1) in MONTHS:
                first = date(int(month.group(2)), MONTHS[month.group(1)], 1)
                topic, link = f"month:{first:%Y-%m}", f"/summary/month/?month={first:%Y-%m}"
            elif assigned:
                task = Task.objects.filter(assigned_to=note.user, title=assigned.group(1)).order_by("-created_at").first()
                link = "/to-do/"
                if task:
                    topic = f"todo:{task.pk}"
                    done = task.done
                else:  # withdrawn since
                    done = True
            elif " completed: " in message:
                link = "/to-do/?show=all"
            elif message.startswith("Document storage is"):
                link = "/"

        fields = {}
        if topic:
            fields["topic"] = topic[:40]
        if link:
            fields["link"] = link
        if done:
            fields.update(dismissed=True, read=True, popped=True)
        if fields:
            Notification.objects.filter(pk=note.pk).update(**fields)


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0016_marketing_spend"),
        ("accounts", "0007_password_requests"),
    ]

    operations = [
        migrations.AddField(
            model_name="followup",
            name="closed_with_lead",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="leadfile",
            name="replaced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="notification",
            name="topic",
            field=models.CharField(blank=True, db_index=True, max_length=40),
        ),
        migrations.AddField(
            model_name="notification",
            name="link",
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.RunPython(tidy, migrations.RunPython.noop),
    ]
