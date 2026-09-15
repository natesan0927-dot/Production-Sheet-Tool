from django.urls import path

from apps.reports import views

app_name = "reports"

urlpatterns = [
    path("", views.index, name="index"),
    path("monthly-sales/", views.monthly_sales_report, name="monthly_sales"),
    path("lost-leads/", views.lost_lead_report, name="lost_leads"),
    path("production/", views.production_report, name="production"),
    path("customers/", views.customer_report, name="customers"),
]
