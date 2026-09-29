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
    ("Installation", "crm:installation_list", "fa-helmet-safety", None),
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


ASSETS = [
    settings.BASE_DIR / "static" / "css" / "app.css",
    settings.BASE_DIR / "static" / "js" / "app.js",
    settings.BASE_DIR / "static" / "js" / "guide.js",
    settings.BASE_DIR / "static" / "js" / "scan.js",
    settings.BASE_DIR / "static" / "js" / "month.js",
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


def _take_popups(user):
    """Anything not yet shown as a pop-up and still worth saying. It stays in the list either way."""
    pending = list(user.notifications.filter(popped=False, dismissed=False).select_related("lead")[:4])
    if pending:
        Notification.objects.filter(pk__in=[n.pk for n in pending]).update(popped=True)
    return pending
