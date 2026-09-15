from django.urls import path

from apps.production import views

app_name = "production"

urlpatterns = [
    path("sheets/", views.ProductionSheetListView.as_view(), name="sheet_list"),
    path("sheets/<int:pk>/", views.ProductionSheetDetailView.as_view(), name="sheet_detail"),
    path("sheets/<int:pk>/items/", views.sheet_save_items, name="sheet_save_items"),
    path("sheets/<int:pk>/submit/", views.sheet_submit, name="sheet_submit"),
    path("sheets/<int:pk>/approve/", views.sheet_approve, name="sheet_approve"),
    path("tasks/<int:pk>/update/", views.task_update, name="task_update"),
    path("qc/", views.QualityCheckListView.as_view(), name="qc_list"),
    path("qc/<int:pk>/", views.qc_detail, name="qc_detail"),
]
