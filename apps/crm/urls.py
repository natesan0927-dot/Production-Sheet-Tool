from django.urls import path

from . import views

app_name = "crm"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    # Salesperson tabs
    path("leads/", views.lead_list, name="lead_list"),
    path("leads/new/", views.lead_create, name="lead_create"),
    path("leads/<int:pk>/", views.lead_detail, name="lead_detail"),
    path("leads/<int:pk>/edit/", views.lead_edit, name="lead_edit"),
    path("pipeline/", views.pipeline, name="pipeline"),
    path("targets/", views.targets, name="targets"),
    path("follow-ups/", views.followups, name="followups"),
    path("lost/", views.lost_opportunities, name="lost_opportunities"),
    path("completed/", views.completed_projects, name="completed_projects"),
    # Stage actions
    path("leads/<int:pk>/measurements/", views.stage_measurements, name="stage_measurements"),
    path("leads/<int:pk>/rough/", views.stage_rough, name="stage_rough"),
    path("leads/<int:pk>/quotation/", views.stage_quotation, name="stage_quotation"),
    path("leads/<int:pk>/won/", views.stage_won, name="stage_won"),
    path("leads/<int:pk>/lost/", views.stage_lost, name="stage_lost"),
    path("leads/<int:pk>/negotiation/", views.toggle_negotiation, name="toggle_negotiation"),
    path("leads/<int:pk>/caf/", views.caf_download, name="caf_download"),
    path("leads/<int:pk>/caf-final/", views.stage_caf_final, name="stage_caf_final"),
    path("leads/<int:pk>/production-sheet/", views.stage_production_sheet, name="stage_production_sheet"),
    path("leads/<int:pk>/production-approve/", views.production_approve, name="production_approve"),
    path("leads/<int:pk>/fabrication/start/", views.fabrication_start, name="fabrication_start"),
    path("leads/<int:pk>/fabrication/checklist/", views.fabrication_checklist, name="fabrication_checklist"),
    path("leads/<int:pk>/fabrication/dispatch-ready/", views.fabrication_to_dispatch, name="fabrication_to_dispatch"),
    path("leads/<int:pk>/dispatch/", views.dispatch, name="dispatch"),
    path("leads/<int:pk>/warranty/", views.warranty_download, name="warranty_download"),
    path("leads/<int:pk>/warranty/upload/", views.warranty_upload, name="warranty_upload"),
    path("leads/<int:pk>/save-project/", views.project_save, name="project_save"),
    path("leads/<int:pk>/follow-up/", views.followup_add, name="followup_add"),
    path("follow-ups/<int:pk>/done/", views.followup_done, name="followup_done"),
    # Role queues
    path("queue/rough-measurements/", views.queue_rough, name="queue_rough"),
    path("queue/final-measurements/", views.queue_final, name="queue_final"),
    path("queue/production-validation/", views.queue_production_validation, name="queue_production_validation"),
    path("queue/quotations/", views.queue_quotations, name="queue_quotations"),
    path("queue/accounts/", views.queue_accounts, name="queue_accounts"),
    path("queue/production/", views.queue_production, name="queue_production"),
    path("queue/fabrication/", views.queue_fabrication, name="queue_fabrication"),
    path("queue/warranty/", views.queue_warranty, name="queue_warranty"),
    path("notifications/", views.notifications, name="notifications"),
]
