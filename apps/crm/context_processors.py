from apps.accounts.models import Role

from .models import Lead

SALES_TABS = [
    ("Dashboard", "crm:dashboard", "fa-gauge-high", None),
    ("Leads", "crm:lead_list", "fa-user-group", None),
    ("Sales Pipeline", "crm:pipeline", "fa-diagram-project", None),
    ("Sales Target", "crm:targets", "fa-bullseye", None),
    ("Follow-up", "crm:followups", "fa-bell", None),
    ("Lost Opportunities", "crm:lost_opportunities", "fa-circle-xmark", None),
    ("Completed Projects", "crm:completed_projects", "fa-circle-check", None),
]

MEASUREMENT_TABS = [
    ("Rough Measurements", "crm:queue_rough", "fa-ruler", "rough"),
    ("Final Measurements", "crm:queue_final", "fa-ruler-combined", "final"),
    ("Production Sheet Validation", "crm:queue_production_validation", "fa-clipboard-check", "validation"),
]

QUOTATION_TABS = [
    ("Quotation Upload", "crm:queue_quotations", "fa-file-invoice", "quotation"),
]

ACCOUNTS_TABS = [
    ("Confirmed Orders", "crm:queue_accounts", "fa-indian-rupee-sign", None),
]

PRODUCTION_TABS = [
    ("Production", "crm:queue_production", "fa-industry", "production"),
    ("Site Fabrication Status", "crm:queue_fabrication", "fa-screwdriver-wrench", "fabrication"),
]

FIELD_MANAGER_TABS = [
    ("Warranty & Handover", "crm:queue_warranty", "fa-shield-halved", "warranty"),
]

ADMIN_TABS = [
    ("Stage Access", "crm:stage_access_list", "fa-user-shield", None),
]

# (section heading, sidebar accent colour, tabs)
SALES_GROUP = ("CRM & Sales", "sales", SALES_TABS)
MEASUREMENT_GROUP = ("Measurement", "measurement", MEASUREMENT_TABS)
QUOTATION_GROUP = ("Quotation", "insights", QUOTATION_TABS)
ACCOUNTS_GROUP = ("Accounts", "payments", ACCOUNTS_TABS)
PRODUCTION_GROUP = ("Production", "production", PRODUCTION_TABS)
FIELD_GROUP = ("Handover", "aftersales", FIELD_MANAGER_TABS)
ADMIN_GROUP = ("Administration", "insights", ADMIN_TABS)

ROLE_GROUPS = {
    Role.SALESPERSON: [SALES_GROUP],
    Role.MEASUREMENT: [MEASUREMENT_GROUP],
    Role.QUOTATION: [QUOTATION_GROUP],
    Role.ACCOUNTS: [ACCOUNTS_GROUP],
    Role.PRODUCTION: [PRODUCTION_GROUP],
    Role.FIELD_MANAGER: [FIELD_GROUP],
    # The Super Admin works every stage, so they get every tab.
    Role.SUPER_ADMIN: [
        SALES_GROUP,
        MEASUREMENT_GROUP,
        QUOTATION_GROUP,
        ACCOUNTS_GROUP,
        PRODUCTION_GROUP,
        FIELD_GROUP,
        ADMIN_GROUP,
    ],
}


def _pending_counts(keys):
    """How many leads are waiting on each queue, for the sidebar badges."""
    counts = {}
    if "rough" in keys:
        counts["rough"] = Lead.objects.filter(
            measurement_mode=Lead.MeasurementMode.REQUESTED,
            measurement_done_at__isnull=True,
            status=Lead.Status.OPEN,
        ).count()
    if "final" in keys:
        counts["final"] = (
            Lead.objects.filter(status=Lead.Status.WON)
            .exclude(caf_signed_at__isnull=False, final_measurement_at__isnull=False)
            .count()
        )
    if "validation" in keys:
        counts["validation"] = Lead.objects.filter(
            production_sheet_at__isnull=False, production_approved_at__isnull=True
        ).count()
    if "quotation" in keys:
        counts["quotation"] = Lead.objects.filter(
            status=Lead.Status.OPEN, measurement_done_at__isnull=False, quotation_uploaded_at__isnull=True
        ).count()
    if "production" in keys:
        counts["production"] = Lead.objects.filter(
            caf_signed_at__isnull=False, final_measurement_at__isnull=False, production_approved_at__isnull=True
        ).count()
    if "fabrication" in keys:
        counts["fabrication"] = Lead.objects.filter(
            production_approved_at__isnull=False, dispatched_at__isnull=True
        ).count()
    if "warranty" in keys:
        counts["warranty"] = Lead.objects.filter(
            dispatched_at__isnull=False, completed_at__isnull=True
        ).count()
    return counts


def navigation(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}

    groups = ROLE_GROUPS.get(user.role, [])
    wanted = {key for _, _, tabs in groups for *_, key in tabs if key}
    counts = _pending_counts(wanted)

    nav_groups = [
        (
            section,
            accent,
            [(label, urlname, icon, counts.get(key)) for label, urlname, icon, key in tabs],
        )
        for section, accent, tabs in groups
    ]
    return {
        "nav_groups": nav_groups,
        "role_label": user.get_role_display(),
        "unread_notifications": user.notifications.filter(read=False).count(),
    }
