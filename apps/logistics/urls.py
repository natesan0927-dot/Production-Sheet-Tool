from django.urls import path

from apps.logistics import views

app_name = "logistics"

urlpatterns = [
    path("dispatch/", views.DispatchListView.as_view(), name="dispatch_list"),
    path("dispatch/<int:pk>/", views.DispatchDetailView.as_view(), name="dispatch_detail"),
    path("dispatch/<int:pk>/update/", views.dispatch_update, name="dispatch_update"),
    path("dispatch/<int:pk>/mark-dispatched/", views.dispatch_mark_dispatched, name="dispatch_mark_dispatched"),

    path("installation/", views.InstallationListView.as_view(), name="installation_list"),
    path("installation/<int:pk>/", views.InstallationDetailView.as_view(), name="installation_detail"),
    path("installation/<int:pk>/update/", views.installation_update, name="installation_update"),
    path("installation/<int:pk>/site-not-ready/", views.installation_site_not_ready, name="installation_site_not_ready"),
    path("installation/<int:pk>/complete/", views.installation_complete, name="installation_complete"),
    path("installation/<int:pk>/handover/", views.installation_handover, name="installation_handover"),
]
