from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    # The service worker has to be served from the site root, or it can only
    # control /static/ — which is the one place it is not needed.
    path(
        "sw.js",
        TemplateView.as_view(template_name="sw.js", content_type="application/javascript"),
        name="service_worker",
    ),
    path("offline/", TemplateView.as_view(template_name="offline.html"), name="offline"),
    path("", include("apps.crm.urls")),
]

# This is a small internal tool with no CDN/object storage in front of it,
# so Django serves uploaded media itself in production too, not just DEBUG.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "Titans Windows — Administration"
admin.site.site_title = "Titans Admin"
admin.site.index_title = "Users & Master Data"
