from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("", include("apps.crm.urls")),
]

# This is a small internal tool with no CDN/object storage in front of it,
# so Django serves uploaded media itself in production too, not just DEBUG.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "Titans Windows — Administration"
admin.site.site_title = "Titans Admin"
admin.site.index_title = "Users & Master Data"
