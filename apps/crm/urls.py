from django.urls import path

from apps.crm import views

app_name = "crm"

urlpatterns = [
    path("customers/", views.CustomerListView.as_view(), name="customer_list"),
    path("customers/add/", views.CustomerCreateView.as_view(), name="customer_create"),
    path("customers/<int:pk>/", views.CustomerDetailView.as_view(), name="customer_detail"),
    path("customers/<int:pk>/edit/", views.CustomerUpdateView.as_view(), name="customer_update"),

    path("leads/", views.LeadListView.as_view(), name="lead_list"),
    path("leads/pipeline/", views.lead_pipeline, name="lead_pipeline"),
    path("leads/add/", views.LeadCreateView.as_view(), name="lead_create"),
    path("leads/<int:pk>/", views.LeadDetailView.as_view(), name="lead_detail"),
    path("leads/<int:pk>/edit/", views.LeadUpdateView.as_view(), name="lead_update"),
    path("leads/<int:pk>/assign/", views.lead_assign, name="lead_assign"),
    path("leads/<int:pk>/followup/", views.followup_create, name="followup_create"),
    path("leads/<int:pk>/won/", views.lead_mark_won, name="lead_mark_won"),
    path("leads/<int:pk>/lost/", views.lead_mark_lost, name="lead_mark_lost"),
]
