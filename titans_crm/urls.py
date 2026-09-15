from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("core/", include("apps.core.urls")),
    path("", include("apps.dashboard.urls")),
    path("crm/", include("apps.crm.urls")),
    path("measurement/", include("apps.measurement.urls")),
    path("sales/", include("apps.sales.urls")),
    path("production/", include("apps.production.urls")),
    path("logistics/", include("apps.logistics.urls")),
    path("aftersales/", include("apps.aftersales.urls")),
    path("reports/", include("apps.reports.urls")),
]

# This is a small internal tool with no CDN/object storage in front of it,
# so Django serves uploaded media itself in production too, not just DEBUG.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "Titans Windows — CRM/ERP Administration"
admin.site.site_title = "Titans CRM Admin"
admin.site.index_title = "Master Data & System Administration"
