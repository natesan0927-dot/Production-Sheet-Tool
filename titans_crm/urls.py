from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView

from .media import serve_upload

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

# Uploaded documents. Django's static() helper is a no-op once DEBUG is off, so
# this route is spelled out — otherwise every file 404s in production. It asks
# for a sign-in first, because these are customer documents.
#
# With a bucket configured the storage backend serves its own signed links and
# nothing reaches here.
if not settings.AWS_STORAGE_BUCKET_NAME:
    urlpatterns += [
        re_path(r"^%s(?P<path>.*)$" % settings.MEDIA_URL.lstrip("/"), serve_upload, name="media"),
    ]

admin.site.site_header = "Titans Windows — Administration"
admin.site.site_title = "Titans Admin"
admin.site.index_title = "Users & Master Data"
