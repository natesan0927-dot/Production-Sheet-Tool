from django.urls import path

from apps.aftersales import views

app_name = "aftersales"

urlpatterns = [
    path("warranty/", views.WarrantyListView.as_view(), name="warranty_list"),
    path("warranty/<int:pk>/", views.WarrantyDetailView.as_view(), name="warranty_detail"),

    path("complaints/", views.ComplaintListView.as_view(), name="complaint_list"),
    path("complaints/add/", views.complaint_create, name="complaint_create"),
    path("complaints/<int:pk>/", views.ComplaintDetailView.as_view(), name="complaint_detail"),
    path("complaints/<int:pk>/update/", views.complaint_update, name="complaint_update"),
]
