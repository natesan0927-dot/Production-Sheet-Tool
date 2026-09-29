"""Updates that tidy themselves away.

Most updates ask someone to do something: measure a site, price a job, approve a
sheet. The moment that is done, by whoever does it, the update has nothing left
to say, so it is cleared for everyone it went to. It leaves "Updates for the
day", stops counting on the bell, and can never pop up late. It stays in the
Notifications list as history.

Each update carries a topic naming what it is waiting for. The view that does
that piece of work clears the topic. Updates that only report news, like "order
confirmed" or "project completed", have no topic and stay until they are ticked
off.
"""

from django.db.models import Q
from django.urls import reverse

from . import push
from .models import Notification

# What an update about a lead is waiting for. The view that does it clears it.
ROUGH = "rough"          # a rough measurement
QUOTATION = "quotation"  # a quotation, first or revised
DECISION = "decision"    # the sales executive's call on a quotation that is out
CAF = "caf"              # the signed CAF and the final measurement
SHEET = "sheet"          # a production sheet, first or redone
APPROVAL = "approval"    # a production sheet approved or sent back
FLOOR = "floor"          # an approved job made and dispatched
INSTALL = "installation" # a dispatched site marked installed
HANDOVER = "handover"    # an installed job handed over

# Nothing about a lead is waiting any more once it is lost.
LEAD_WORK = (ROUGH, QUOTATION, DECISION, CAF, SHEET, APPROVAL, FLOOR, INSTALL, HANDOVER)

LENGTH = Notification._meta.get_field("message").max_length


def todo(task):
    return f"todo:{task.pk}"


def todo_finished(task):
    """The news, to whoever handed it out, that a to-do was completed."""
    return f"todo-done:{task.pk}"


def complaint(item):
    return f"complaint:{item.pk}"


def password(user):
    return f"password:{user.pk}"


def month(first):
    return f"month:{first:%Y-%m}"


def fit(message):
    """Messages are kept to what the column holds; Postgres refuses anything longer."""
    message = " ".join(str(message).split())
    return message if len(message) <= LENGTH else message[: LENGTH - 1] + "…"


def send(users, message, lead=None, topic="", link=""):
    """One update each for these people. Anyone listed twice, or no one, is fine.

    Each is also pushed to the person's phone, where they turned notifications on.
    """
    seen, notes = set(), []
    for user in users:
        if user is None or user.pk in seen:
            continue
        seen.add(user.pk)
        notes.append(Notification(user=user, lead=lead, message=fit(message), topic=topic, link=link))
    Notification.objects.bulk_create(notes)
    push.deliver(notes)
    return notes


def clear(*topics, lead=None, user=None):
    """Everyone's copies of these updates are dealt with. Returns how many were cleared."""
    notes = Notification.objects.filter(topic__in=topics).filter(
        Q(dismissed=False) | Q(read=False) | Q(popped=False)
    )
    if lead is not None:
        notes = notes.filter(lead=lead)
    if user is not None:
        notes = notes.filter(user=user)
    return notes.update(dismissed=True, read=True, popped=True)


def clear_for(user, lead):
    """A lead moved to someone else: what its old owner was told no longer concerns them."""
    return Notification.objects.filter(user=user, lead=lead).update(dismissed=True, read=True, popped=True)


# ---------------------------------------------------------------- where lead-less updates open
def todo_link():
    return reverse("crm:todo_list")


def complaints_link():
    return reverse("crm:complaint_list")


def completed_link(lead):
    return f"{reverse('crm:completed_projects')}?q={lead.lead_number}"


def employees_link():
    return reverse("accounts:employee_list") + "#password-requests"


def month_link(first):
    return f"{reverse('crm:month_summary')}?month={first:%Y-%m}"
