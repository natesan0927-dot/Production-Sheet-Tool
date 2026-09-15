from apps.core.access import primary_role_label, user_sections
from apps.core.models import CompanyProfile


def company_and_notifications(request):
    context = {"company": CompanyProfile.load()}
    if request.user.is_authenticated:
        qs = request.user.notifications.all()
        context["nav_notifications"] = qs[:8]
        context["unread_notification_count"] = qs.filter(is_read=False).count()
        context["nav_sections"] = user_sections(request.user)
        context["role_label"] = primary_role_label(request.user)
    return context
