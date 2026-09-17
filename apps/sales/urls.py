from django.urls import path

from apps.sales import views

app_name = "sales"

urlpatterns = [
    path("quotations/request/<int:lead_pk>/", views.quotation_request, name="quotation_request"),
    path("quotations/", views.QuotationListView.as_view(), name="quotation_list"),
    path("quotations/add/", views.quotation_create, name="quotation_create"),
    path("quotations/<int:pk>/", views.QuotationDetailView.as_view(), name="quotation_detail"),
    path("quotations/<int:pk>/revise/", views.quotation_revise, name="quotation_revise"),
    path("quotations/<int:pk>/send/", views.quotation_send, name="quotation_send"),

    path("orders/", views.OrderListView.as_view(), name="order_list"),
    path("orders/confirm/", views.order_create, name="order_create"),
    path("orders/<int:pk>/", views.OrderDetailView.as_view(), name="order_detail"),
    path("orders/<int:pk>/payment/", views.payment_add, name="payment_add"),
    path("orders/<int:pk>/caf/regenerate/", views.caf_regenerate, name="caf_regenerate"),
    path("orders/<int:pk>/invoiced/", views.order_mark_invoiced, name="order_mark_invoiced"),

    path("payments/", views.payment_dashboard, name="payment_dashboard"),

    path("targets/", views.TargetListView.as_view(), name="target_list"),
    path("targets/add/", views.target_create, name="target_create"),
]
