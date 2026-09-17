"""
Single source of truth for role-based navigation and page access, so the
sidebar (what a role *sees*) and the views (what a role is actually *allowed
to open*) never drift apart.

Section keys are also used directly as Django group-permission checks via
RoleRequiredMixin(section=...).
"""

SUPER = "Super Admin"
MANAGEMENT = "Management"

SECTION_ROLES = {
    "crm_sales": [SUPER, MANAGEMENT, "Sales Manager", "Salesperson", "Quotation Staff", "Admin Staff"],
    "measurement": [SUPER, MANAGEMENT, "Sales Manager", "Salesperson", "Measurement Staff", "Admin Staff"],
    "production": [SUPER, MANAGEMENT, "Admin Staff", "Production Manager", "Production Staff", "Quality Control"],
    "dispatch": [SUPER, MANAGEMENT, "Admin Staff", "Dispatch Staff", "Production Manager"],
    "installation": [SUPER, MANAGEMENT, "Admin Staff", "Installation Team"],
    "aftersales": [SUPER, MANAGEMENT, "Admin Staff", "Service/Maintenance Staff"],
    "insights": [SUPER, MANAGEMENT, "Sales Manager", "Production Manager", "Admin Staff"],
    "people": [SUPER, MANAGEMENT, "Admin Staff"],
    "settings": [SUPER, "Admin Staff"],
    "payments": [SUPER, MANAGEMENT, "Accounts Staff"],
}

# Human labels for the little role badge shown next to the user's name.
ROLE_PRIORITY = [
    SUPER, MANAGEMENT, "Sales Manager", "Salesperson", "Quotation Staff", "Measurement Staff",
    "Admin Staff", "Production Manager", "Production Staff", "Quality Control", "Dispatch Staff",
    "Installation Team", "Service/Maintenance Staff", "Accounts Staff",
]


def user_sections(user):
    """Set of section keys this user may see/open."""
    if not user.is_authenticated:
        return set()
    if user.is_superuser or user.is_staff:
        return set(SECTION_ROLES.keys())
    roles = set(user.groups.values_list("name", flat=True))
    return {section for section, allowed in SECTION_ROLES.items() if roles.intersection(allowed)}


def primary_role_label(user):
    if user.is_superuser:
        return "Super Admin"
    roles = set(user.groups.values_list("name", flat=True))
    for name in ROLE_PRIORITY:
        if name in roles:
            return name
    return "Employee"
