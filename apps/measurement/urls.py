from django.urls import path

from apps.measurement import views

app_name = "measurement"

urlpatterns = [
    path("requests/", views.MeasurementRequestListView.as_view(), name="request_list"),
    path("requests/add/", views.request_create, name="request_create"),
    path("requests/<int:pk>/", views.MeasurementRequestDetailView.as_view(), name="request_detail"),
    path("requests/<int:pk>/items/", views.request_save_items, name="request_save_items"),
    path("requests/<int:pk>/upload/", views.request_upload_attachment, name="request_upload"),
    path("requests/<int:pk>/complete/", views.request_complete, name="request_complete"),

    path("final/", views.FinalMeasurementListView.as_view(), name="final_list"),
    path("final/add/", views.final_create, name="final_create"),
    path("final/<int:pk>/", views.FinalMeasurementDetailView.as_view(), name="final_detail"),
    path("final/<int:pk>/items/", views.final_save_items, name="final_save_items"),
    path("final/<int:pk>/site-not-ready/", views.final_site_not_ready, name="final_site_not_ready"),
    path("final/<int:pk>/site-ready/", views.final_site_ready, name="final_site_ready"),
    path("final/<int:pk>/approve/", views.final_approve, name="final_approve"),
]
