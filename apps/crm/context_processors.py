from datetime import timedelta

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts import recovery
from apps.accounts.models import Role, User

from . import guide as guide_content
from . import monthly, queues, storage_usage, updates
from .models import FollowUp, Lead, Notification, Task

# Fetched by the browser in the background, never looked at by a person. Rendering
# them must not use up pop-ups or run the Super Admin's reminders.
BACKGROUND_PATHS = ("/sw.js", "/offline/")


def _for_a_person(request):
    """The signed-in user, unless this request is one the browser makes on its own."""
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated) or request.path in BACKGROUND_PATHS:
        return None
    return user

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

# A tab that opens into pages of its own: (label, None, icon, badge key, children),
# each child being (label, url name, badge key).
INSTALLATION_TAB = (
    "Installation", None, "fa-helmet-safety", "installation",
    [
        ("Awaiting Installation", "crm:installation_pending", "installation"),
        ("Installation Ledger", "crm:installation_list", None),
    ],
)

PRODUCTION_TABS = [
    ("Production", "crm:queue_production", "fa-industry", "production"),
    ("Site Fabrication Status", "crm:queue_fabrication", "fa-screwdriver-wrench", "fabrication"),
    INSTALLATION_TAB,
]

FIELD_MANAGER_TABS = [
    ("Warranty & Handover", "crm:queue_warranty", "fa-shield-halved", "warranty"),
    ("Service Requests", "crm:complaint_list", "fa-screwdriver", "complaints"),
]

ADMIN_TABS = [
    ("Summary for the Day", "crm:day_summary", "fa-calendar-day", None),
    ("Summary for the Month", "crm:month_summary", "fa-calendar-days", None),
    ("Employees", "accounts:employee_list", "fa-users", "passwords"),
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
# For anyone outside production the Super Admin has given the Installation step.
INSTALLATION_GROUP = ("Installation", "production", [INSTALLATION_TAB])

# Monitoring is a section of its own, for the Super Admin and the sales executives:
# the CRM's sidebar has a way in, and inside it the sidebar is Monitoring's.
MONITORING_ENTRY = ("Monitoring", "logistics", [("Monitoring", "monitoring:home", "fa-binoculars", None)])
MONITORING_GROUPS = {
    Role.SUPER_ADMIN: [
        ("Monitoring", "production", [
            ("Attendance", "monitoring:attendance", "fa-clipboard-user", None),
            ("Employees", "monitoring:employees", "fa-people-group", None),
            ("Salary & Advances", "monitoring:salary", "fa-wallet", None),
            ("Reports", "monitoring:reports", "fa-file-excel", None),
            ("Site Visits", "monitoring:status", "fa-location-dot", None),
        ]),
    ],
    Role.SALESPERSON: [
        ("Monitoring", "production", [
            ("Today's Work", "monitoring:work", "fa-person-walking-arrow-right", None),
            ("Site Visits", "monitoring:status", "fa-location-dot", None),
        ]),
    ],
}
BACK_TO_CRM = ("Titans CRM", "sales", [("Back to the CRM", "crm:dashboard", "fa-arrow-left", None)])
MONITORING_PATH = "/monitoring/"

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
    "fabrication", "installation", "warranty", "complaints", "todo", "followup",
}


def _pending_counts(keys, user):
    """How many are waiting on each queue — the same lists the queue pages show."""
    counts = {}
    if "rough" in keys:
        counts["rough"] = queues.rough_for(user).count()
    if "final" in keys:
        counts["final"] = queues.final().count()
    if "validation" in keys:
        counts["validation"] = queues.validation().count()
    if "quotation" in keys:
        counts["quotation"] = queues.quotation().count()
    if "production" in keys:
        counts["production"] = queues.production().count()
    if "fabrication" in keys:
        counts["fabrication"] = queues.floor().count()
    if "installation" in keys:
        counts["installation"] = queues.installation().count()
    if "complaints" in keys:
        counts["complaints"] = queues.complaints().count()
    if "todo" in keys:
        counts["todo"] = Task.objects.filter(assigned_to=user, done=False).count()
    if "followup" in keys:
        # Everything still open, whatever its date — it stays counted until marked done.
        open_followups = FollowUp.objects.filter(done=False, lead__status=Lead.Status.OPEN)
        if user.role == Role.SALESPERSON:
            open_followups = open_followups.filter(lead__assigned_to=user)
        counts["followup"] = open_followups.count()
    if "passwords" in keys:
        counts["passwords"] = recovery.open_requests().count()
    if "warranty" in keys:
        counts["warranty"] = queues.handover().count()
    return counts


FABRICATION_COLUMNS = [
    (Lead.Fabrication.FUTURE, "Future Production"),
    (Lead.Fabrication.UNDER, "Under Production"),
    (Lead.Fabrication.READY, "Ready for Dispatch"),
]


def _fabrication_children(request, url):
    """The Super Admin's Site Fabrication tab opens into its three columns."""
    on_floor = queues.floor()
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


def _groups_for(user, path=""):
    """The sidebar's sections for this person — their role's, plus any step handed to them.

    Inside Monitoring the sidebar is Monitoring's own, with a way back.
    """
    from . import stages

    if path.startswith(MONITORING_PATH) and user.role in MONITORING_GROUPS:
        return [*MONITORING_GROUPS[user.role], BACK_TO_CRM]
    groups = list(ROLE_GROUPS.get(user.role, []))
    has_installation = any(tab is INSTALLATION_TAB for _, _, tabs in groups for tab in tabs)
    if not has_installation and stages.can_act(user, stages.INSTALLATION):
        groups.insert(max(len(groups) - 1, 0), INSTALLATION_GROUP)
    if user.role in MONITORING_GROUPS:
        groups.append(MONITORING_ENTRY)
    return groups


def _parent_item(request, label, icon, pending, children, counts):
    """A tab that opens in place to show its own pages, like Installation."""
    built = [
        {"label": child_label, "url": reverse(child_url), "url_name": child_url, "count": counts.get(child_key)}
        for child_label, child_url, child_key in children
    ]
    # The page open now belongs to whichever child's address it starts with, most specific first.
    here = max((child for child in built if request.path.startswith(child["url"])),
               key=lambda child: len(child["url"]), default=None)
    for child in built:
        child["active"] = child is here
    return {
        "label": label,
        "url": built[0]["url"],
        "url_name": None,
        "icon": icon,
        "pending": pending,
        "active": here is not None,
        "children": built,
    }


ASSETS = [
    settings.BASE_DIR / "static" / "css" / "app.css",
    settings.BASE_DIR / "static" / "js" / "app.js",
    settings.BASE_DIR / "static" / "js" / "guide.js",
    settings.BASE_DIR / "static" / "js" / "scan.js",
    settings.BASE_DIR / "static" / "js" / "month.js",
    settings.BASE_DIR / "static" / "js" / "push.js",
    settings.BASE_DIR / "static" / "js" / "monitoring.js",
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


def navigation(request, take_popups=True):
    context = {"css_version": _stylesheet_version()}
    user = _for_a_person(request)
    if not user:
        return context

    groups = _groups_for(user, request.path)
    wanted = set()
    for _, _, tabs in groups:
        for tab in tabs:
            wanted.add(tab[3])
            wanted.update(child[2] for child in (tab[4] if len(tab) > 4 else []))
    wanted.discard(None)
    counts = _pending_counts(wanted, user)

    nav_groups = []
    for section, accent, tabs in groups:
        items = []
        for tab in tabs:
            label, urlname, icon, key = tab[:4]
            if len(tab) > 4:
                items.append(_parent_item(request, label, icon, counts.get(key), tab[4], counts))
                continue
            url = reverse(urlname)
            item = {
                "label": label,
                "url": url,
                "url_name": urlname,
                "icon": icon,
                "pending": counts.get(key),
                # A Monitoring tab stays lit on the pages inside it (one employee, one month).
                "active": request.path == url or (url.startswith(MONITORING_PATH) and url != MONITORING_PATH
                                                  and request.path.startswith(url)),
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
            "popup_notifications": _take_popups(user) if take_popups and user.intro_seen_at else [],
            # The tour runs across pages, so every page needs to know the steps.
            "tour_steps": guide_content.tour_for(nav_groups),
        }
    )
    if user.intro_seen_at is None:
        context["intro"] = guide_content.intro_for(user)
    return context


def storage(request):
    """How full the document bucket is — for the Super Admin, and no one else."""
    user = _for_a_person(request)
    if not (user and user.is_super_admin):
        return {}
    return {"storage_usage": storage_usage.current()}


def month_end(request):
    """On the last day of the month, tell the Super Admin the summary is ready. Once."""
    user = _for_a_person(request)
    if not (user and user.is_super_admin):
        return {}
    today = timezone.localdate()
    if not monthly.is_last_day(today):
        return {}

    from django.core.cache import cache

    key = f"month-summary-reminded-{today:%Y-%m}"
    if not cache.get(key):
        first = monthly.month_start(today)
        message = f"Summary for the Month — {today:%B %Y} is ready under Administration."
        # The message names the month, so finding it lately is enough to know it went out —
        # even after a restart has emptied the cache.
        recently = timezone.now() - timedelta(days=3)
        already = Notification.objects.filter(message=message, created_at__gte=recently).values_list("user_id", flat=True)
        admins = User.objects.filter(role=Role.SUPER_ADMIN, is_active=True).exclude(pk__in=list(already))
        updates.send(admins, message, topic=updates.month(first), link=updates.month_link(first))
        cache.set(key, True, 60 * 60 * 24)
    return {}


def reminders(request):
    """Reminders that are due by the calendar — a late installation — go out as people use the app."""
    if _for_a_person(request):
        from . import reminders as due

        try:
            due.check()
        except Exception:  # a reminder must never break the page someone opened
            import logging

            logging.getLogger(__name__).warning("Could not send due reminders", exc_info=True)
    return {}


def _take_popups(user):
    """Anything not yet shown as a pop-up and still worth saying. It stays in the list either way."""
    pending = list(user.notifications.filter(popped=False, dismissed=False).select_related("lead")[:4])
    if pending:
        Notification.objects.filter(pk__in=[n.pk for n in pending]).update(popped=True)
    return pending
