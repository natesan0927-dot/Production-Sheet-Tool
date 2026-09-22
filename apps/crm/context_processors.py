from apps.accounts.models import Role

SALES_TABS = [
    ("Dashboard", "crm:dashboard", "fa-gauge-high"),
    ("Leads", "crm:lead_list", "fa-user-group"),
    ("Sales Pipeline", "crm:pipeline", "fa-diagram-project"),
    ("Sales Target", "crm:targets", "fa-bullseye"),
    ("Follow-up", "crm:followups", "fa-bell"),
    ("Lost Opportunities", "crm:lost_opportunities", "fa-circle-xmark"),
    ("Completed Projects", "crm:completed_projects", "fa-circle-check"),
]

MEASUREMENT_TABS = [
    ("Rough Measurements", "crm:queue_rough", "fa-ruler"),
    ("Final Measurements", "crm:queue_final", "fa-ruler-combined"),
    ("Production Sheet Validation", "crm:queue_production_validation", "fa-clipboard-check"),
]

ACCOUNTS_TABS = [
    ("Quotations", "crm:queue_quotations", "fa-file-invoice"),
    ("Confirmed Orders", "crm:queue_accounts", "fa-indian-rupee-sign"),
]

PRODUCTION_TABS = [
    ("Production", "crm:queue_production", "fa-industry"),
    ("Site Fabrication Status", "crm:queue_fabrication", "fa-screwdriver-wrench"),
]

FIELD_MANAGER_TABS = [
    ("Warranty & Handover", "crm:queue_warranty", "fa-shield-halved"),
]

# (section heading, sidebar accent colour, tabs)
SALES_GROUP = ("CRM & Sales", "sales", SALES_TABS)
MEASUREMENT_GROUP = ("Measurement", "measurement", MEASUREMENT_TABS)
ACCOUNTS_GROUP = ("Accounts", "payments", ACCOUNTS_TABS)
PRODUCTION_GROUP = ("Production", "production", PRODUCTION_TABS)
FIELD_GROUP = ("Handover", "aftersales", FIELD_MANAGER_TABS)

ROLE_GROUPS = {
    Role.SALESPERSON: [SALES_GROUP],
    Role.MEASUREMENT: [MEASUREMENT_GROUP],
    Role.ACCOUNTS: [ACCOUNTS_GROUP],
    Role.PRODUCTION: [PRODUCTION_GROUP],
    Role.FIELD_MANAGER: [FIELD_GROUP],
    # The Super Admin works every stage, so they get every tab.
    Role.SUPER_ADMIN: [SALES_GROUP, MEASUREMENT_GROUP, ACCOUNTS_GROUP, PRODUCTION_GROUP, FIELD_GROUP],
}


def navigation(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    return {
        "nav_groups": ROLE_GROUPS.get(user.role, []),
        "role_label": user.get_role_display(),
        "unread_notifications": user.notifications.filter(read=False).count(),
    }
