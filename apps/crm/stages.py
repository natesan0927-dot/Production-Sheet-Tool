"""The eight-stage journey every lead follows, and who may act at each stage."""

from apps.accounts.models import Role

from .models import Lead

LEAD = "lead"
ROUGH = "rough"
QUOTATION = "quotation"
DECISION = "decision"
CAF = "caf"
PRODUCTION = "production"
FABRICATION = "fabrication"
WARRANTY = "warranty"

STAGE_DEFS = [
    (LEAD, "Lead Created", (Role.SALESPERSON,)),
    (ROUGH, "Rough Measurement", (Role.MEASUREMENT,)),
    (QUOTATION, "Quotation", (Role.QUOTATION,)),
    (DECISION, "Follow-up / Won-Lost", (Role.SALESPERSON,)),
    (CAF, "CAF & Final Measurement", (Role.MEASUREMENT,)),
    (PRODUCTION, "Production", (Role.PRODUCTION,)),
    (FABRICATION, "Site Fabrication Status", (Role.PRODUCTION,)),
    (WARRANTY, "Warranty & Handover", (Role.FIELD_MANAGER,)),
]

ALL_STAGE_KEYS = [key for key, _, _ in STAGE_DEFS]
STAGE_ROLES = {key: roles for key, _, roles in STAGE_DEFS}
STAGE_LABELS = {key: label for key, label, _ in STAGE_DEFS}

# By default a role only sees the steps it actually works on. The Super Admin
# can widen or narrow this per employee (accounts.User.visible_stages).
DEFAULT_ROLE_STAGES = {
    Role.SALESPERSON: ALL_STAGE_KEYS,
    Role.SUPER_ADMIN: ALL_STAGE_KEYS,
    Role.MEASUREMENT: [ROUGH, CAF, PRODUCTION],
    Role.QUOTATION: [QUOTATION],
    Role.ACCOUNTS: [DECISION],
    Role.PRODUCTION: [PRODUCTION, FABRICATION],
    Role.FIELD_MANAGER: [WARRANTY],
}

# Order values, advances and balances are only for the people who deal in them.
FINANCIAL_ROLES = (Role.SALESPERSON, Role.ACCOUNTS, Role.SUPER_ADMIN)


def visible_stage_keys(user):
    chosen = [key for key in (user.visible_stages or []) if key in STAGE_ROLES]
    if chosen:
        return chosen
    return DEFAULT_ROLE_STAGES.get(user.role, ALL_STAGE_KEYS)


def can_see_financials(user):
    return user.role in FINANCIAL_ROLES


def _is_done(lead, key):
    if key == LEAD:
        return bool(lead.measurement_mode)
    if key == ROUGH:
        return lead.measurement_done_at is not None
    if key == QUOTATION:
        return lead.quotation_uploaded_at is not None
    if key == DECISION:
        return lead.status == Lead.Status.WON
    if key == CAF:
        return lead.caf_signed_at is not None and lead.final_measurement_at is not None
    if key == PRODUCTION:
        return lead.production_approved_at is not None
    if key == FABRICATION:
        return lead.dispatched_at is not None
    if key == WARRANTY:
        return lead.completed_at is not None
    return False


def current_stage_key(lead):
    """The first stage that still needs work, or None when the lead is finished."""
    if lead.status == Lead.Status.LOST:
        return DECISION
    for key, _, _ in STAGE_DEFS:
        if not _is_done(lead, key):
            return key
    return None


def build_stages(lead, user=None):
    """Per-stage state for the stepper and the stacked stage panels."""
    lost = lead.status == Lead.Status.LOST
    current = current_stage_key(lead)
    allowed = visible_stage_keys(user) if user else ALL_STAGE_KEYS
    stages = []
    for index, (key, label, roles) in enumerate(STAGE_DEFS, start=1):
        if key not in allowed:
            continue
        done = _is_done(lead, key)
        if lost and key == DECISION:
            state = "lost"
        elif done:
            state = "done"
        elif key == current and not lost:
            state = "current"
        else:
            state = "locked"
        stages.append(
            {
                "key": key,
                "number": index,
                "label": label,
                "state": state,
                "roles": roles,
                "can_act": bool(user and user.has_role(*roles)),
                "role_names": ", ".join(Role(r).label for r in roles),
            }
        )
    return stages


def can_act(user, stage_key):
    return user.has_role(*STAGE_ROLES[stage_key])
