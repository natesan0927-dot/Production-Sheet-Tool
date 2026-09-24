from django.conf import settings
from django.db.models import Q
from django.urls import reverse

from apps.accounts.models import Role

from . import guide as guide_content
from .models import FollowUp, Lead, Notification, ServiceComplaint, Task

SALES_TABS = [
    ("Dashboard", "crm:dashboard", "fa-gauge-high", None),
    ("Leads", "crm:lead_list", "fa-user-group", None),
    ("Sales Pipeline", "crm:pipeline", "fa-diagram-project", None),
    ("Sales Target", "crm:targets", "fa-bullseye", None),
    ("Follow-up", "crm:followups", "fa-bell", "followup"),
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
    ("Accounts", "crm:queue_accounts", "fa-indian-rupee-sign", None),
]

PRODUCTION_TABS = [
    ("Production", "crm:queue_production", "fa-industry", "production"),
    ("Site Fabrication Status", "crm:queue_fabrication", "fa-screwdriver-wrench", "fabrication"),
]

FIELD_MANAGER_TABS = [
    ("Warranty & Handover", "crm:queue_warranty", "fa-shield-halved", "warranty"),
    ("Service Requests", "crm:complaint_list", "fa-screwdriver", "complaints"),
]

ADMIN_TABS = [
    ("Summary for the Day", "crm:day_summary", "fa-calendar-day", None),
    ("Stage Access", "crm:stage_access_list", "fa-user-shield", None),
]

TODO_TABS = [
    ("Dashboard", "crm:dashboard", "fa-gauge-high", None),
    ("To-Do", "crm:todo_list", "fa-list-check", "todo"),
    ("Guide", "crm:guide", "fa-circle-play", None),
]

TODO_GROUP = ("My Work", "logistics", TODO_TABS)
# The salesperson already has a Dashboard tab of their own.
SALES_TODO_GROUP = ("My Work", "logistics", TODO_TABS[1:])

# (section heading, sidebar accent colour, tabs)
SALES_GROUP = ("CRM & Sales", "sales", SALES_TABS)
MEASUREMENT_GROUP = ("Measurement", "measurement", MEASUREMENT_TABS)
QUOTATION_GROUP = ("Quotation", "insights", QUOTATION_TABS)
ACCOUNTS_GROUP = ("Accounts", "payments", ACCOUNTS_TABS)
PRODUCTION_GROUP = ("Production", "production", PRODUCTION_TABS)
FIELD_GROUP = ("Handover", "aftersales", FIELD_MANAGER_TABS)
ADMIN_GROUP = ("Administration", "insights", ADMIN_TABS)

ROLE_GROUPS = {
    Role.SALESPERSON: [SALES_GROUP, SALES_TODO_GROUP],
    Role.MEASUREMENT: [MEASUREMENT_GROUP, TODO_GROUP],
    Role.QUOTATION: [QUOTATION_GROUP, TODO_GROUP],
    Role.ACCOUNTS: [ACCOUNTS_GROUP, TODO_GROUP],
    Role.PRODUCTION: [PRODUCTION_GROUP, TODO_GROUP],
    Role.FIELD_MANAGER: [FIELD_GROUP, TODO_GROUP],
    # The Super Admin works every stage, so they get every tab.
    Role.SUPER_ADMIN: [
        SALES_GROUP,
        MEASUREMENT_GROUP,
        QUOTATION_GROUP,
        ACCOUNTS_GROUP,
        PRODUCTION_GROUP,
        FIELD_GROUP,
        SALES_TODO_GROUP,
        ADMIN_GROUP,
    ],
}


ALL_QUEUE_KEYS = {
    "rough", "final", "validation", "quotation", "production",
    "fabrication", "warranty", "complaints", "todo", "followup",
}


def _pending_counts(keys, user):
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
            Q(quotation_uploaded_at__isnull=True) | Q(quotation_revision_pending=True),
            status=Lead.Status.OPEN,
            measurement_done_at__isnull=False,
        ).count()
    if "production" in keys:
        counts["production"] = Lead.objects.filter(
            caf_signed_at__isnull=False, final_measurement_at__isnull=False, production_approved_at__isnull=True
        ).count()
    if "fabrication" in keys:
        counts["fabrication"] = Lead.objects.filter(
            production_approved_at__isnull=False, dispatched_at__isnull=True
        ).count()
    if "complaints" in keys:
        counts["complaints"] = ServiceComplaint.objects.filter(resolved_at__isnull=True).count()
    if "todo" in keys:
        counts["todo"] = Task.objects.filter(assigned_to=user, done=False).count()
    if "followup" in keys:
        # Everything still open, whatever its date — it stays counted until marked done.
        open_followups = FollowUp.objects.filter(done=False)
        if user.role == Role.SALESPERSON:
            open_followups = open_followups.filter(lead__assigned_to=user)
        counts["followup"] = open_followups.count()
    if "warranty" in keys:
        counts["warranty"] = Lead.objects.filter(
            dispatched_at__isnull=False, completed_at__isnull=True
        ).count()
    return counts


FABRICATION_COLUMNS = [
    (Lead.Fabrication.FUTURE, "Future Production"),
    (Lead.Fabrication.UNDER, "Under Production"),
    (Lead.Fabrication.READY, "Ready for Dispatch"),
]


def _fabrication_children(request, url):
    """The Super Admin's Site Fabrication tab opens into its three columns."""
    on_floor = Lead.objects.filter(status=Lead.Status.WON, dispatched_at__isnull=True)
    here = request.path == url
    selected = request.GET.get("column") or Lead.Fabrication.FUTURE
    return [
        {
            "label": label,
            "url": f"{url}?column={key}",
            "count": on_floor.filter(fabrication_column=key).count(),
            "active": here and selected == key,
        }
        for key, label in FABRICATION_COLUMNS
    ]


ASSETS = [
    settings.BASE_DIR / "static" / "css" / "app.css",
    settings.BASE_DIR / "static" / "js" / "app.js",
]


def _stylesheet_version():
    """Changes whenever the stylesheet or script does, so no stale copies."""
    stamps = []
    for asset in ASSETS:
        try:
            stamps.append(int(asset.stat().st_mtime))
        except OSError:
            pass
    return max(stamps) if stamps else 0


def navigation(request):
    context = {"css_version": _stylesheet_version()}
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return context

    groups = ROLE_GROUPS.get(user.role, [])
    wanted = {key for _, _, tabs in groups for *_, key in tabs if key}
    counts = _pending_counts(wanted, user)

    nav_groups = []
    for section, accent, tabs in groups:
        items = []
        for label, urlname, icon, key in tabs:
            url = reverse(urlname)
            item = {
                "label": label,
                "url": url,
                "url_name": urlname,
                "icon": icon,
                "pending": counts.get(key),
                "active": request.path == url,
                "children": [],
            }
            if urlname == "crm:queue_fabrication" and user.is_super_admin:
                item["children"] = _fabrication_children(request, url)
                # Each sub-item counts its own table's rows, so the parent needn't.
                item["pending"] = None
                # Stay open anywhere inside the fabrication screens.
                item["active"] = request.path.startswith(url)
            items.append(item)
        nav_groups.append((section, accent, items))

    context.update(
        {
            "nav_groups": nav_groups,
            "role_label": user.get_role_display(),
            "unread_notifications": user.notifications.filter(read=False).count(),
            # The walkthrough plays once, on the first sign-in. It suppresses the
            # pop-ups for that visit so the two don't talk over each other.
            "show_intro": user.intro_seen_at is None,
            "popup_notifications": [] if user.intro_seen_at is None else _take_popups(user),
            # The tour runs across pages, so every page needs to know the steps.
            "tour_steps": guide_content.tour_for(nav_groups),
        }
    )
    if user.intro_seen_at is None:
        context["intro"] = guide_content.intro_for(user)
    return context


def _take_popups(user):
    """Anything not yet shown as a pop-up. It stays in the list either way."""
    pending = list(user.notifications.filter(popped=False).select_related("lead")[:4])
    if pending:
        Notification.objects.filter(pk__in=[n.pk for n in pending]).update(popped=True)
    return pending
