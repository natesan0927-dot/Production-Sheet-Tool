"""What is waiting on each team.

The sidebar badges, the dashboard tiles and the queue pages all read these, so a
number can never disagree with the list it opens, and it drops the moment the
work is done.
"""

from django.db.models import Q

from apps.accounts.models import Role

from .models import Lead, ServiceComplaint


def rough():
    """Rough measurements asked for and not yet recorded."""
    return Lead.objects.filter(
        measurement_mode=Lead.MeasurementMode.REQUESTED,
        measurement_done_at__isnull=True,
        status=Lead.Status.OPEN,
    )


def rough_for(user):
    """A job allocated to one person is theirs; one left open is anyone's on the team."""
    leads = rough()
    if user.role == Role.MEASUREMENT:
        leads = leads.filter(Q(measurement_assigned_to=user) | Q(measurement_assigned_to__isnull=True))
    return leads


def final():
    """Confirmed orders still missing the signed CAF or the final measurement."""
    return Lead.objects.filter(status=Lead.Status.WON).exclude(
        caf_signed_at__isnull=False, final_measurement_at__isnull=False
    )


def validation():
    """Production sheets waiting for the measurement staff — not ones they sent back."""
    return Lead.objects.filter(
        production_sheet_at__isnull=False,
        production_approved_at__isnull=True,
        production_revision_at__isnull=True,
    )


def quotation():
    """Measured and waiting for a first quotation, or for a revision the sales executive asked for."""
    return Lead.objects.filter(
        Q(quotation_uploaded_at__isnull=True) | Q(quotation_revision_pending=True),
        status=Lead.Status.OPEN,
        measurement_done_at__isnull=False,
    )


def production():
    """Orders the production team owes a sheet for: none uploaded yet, or one sent back."""
    return Lead.objects.filter(
        caf_signed_at__isnull=False,
        final_measurement_at__isnull=False,
        production_approved_at__isnull=True,
    ).filter(Q(production_sheet_at__isnull=True) | Q(production_revision_at__isnull=False))


def floor():
    """Every confirmed order not yet dispatched — what the Site Fabrication list shows."""
    return Lead.objects.filter(status=Lead.Status.WON, dispatched_at__isnull=True)


def handover():
    """Dispatched and waiting for the signed handover."""
    return Lead.objects.filter(dispatched_at__isnull=False, completed_at__isnull=True)


def complaints():
    return ServiceComplaint.objects.filter(resolved_at__isnull=True)
