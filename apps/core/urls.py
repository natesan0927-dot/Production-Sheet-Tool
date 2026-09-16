from django.urls import path

from apps.core import views

app_name = "core"

urlpatterns = [
    path("export/<str:app_label>/<str:model>/<int:pk>/", views.local_copy_download, name="local_copy"),
    path("notifications/poll/", views.notifications_poll, name="notifications_poll"),
    path("notifications/", views.notification_list, name="notifications"),
    path("notifications/<int:pk>/read/", views.notification_mark_read, name="notification_read"),
    path("notifications/read-all/", views.notification_mark_all_read, name="notifications_read_all"),
    path("search/", views.global_search, name="search"),
    path("settings/", views.settings_hub, name="settings_hub"),
    path("guide/", views.guide, name="guide"),
]
