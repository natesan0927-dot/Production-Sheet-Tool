from django.urls import path

from . import views

app_name = "monitoring"

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.MonitoringLoginView.as_view(), name="login"),
    # The Super Admin
    path("employees/", views.employees, name="employees"),
    path("employees/new/", views.employee_add, name="employee_add"),
    path("employees/<int:pk>/", views.employee, name="employee"),
    path("employees/<int:pk>/edit/", views.employee_edit, name="employee_edit"),
    path("employees/<int:pk>/remove/", views.employee_remove, name="employee_remove"),
    path("employees/<int:pk>/restore/", views.employee_restore, name="employee_restore"),
    path("employees/<int:pk>/day/", views.employee_day, name="employee_day"),
    path("employees/<int:pk>/report/", views.report_to_date, name="report_to_date"),
    path("employees/<int:pk>/report/<str:month>/", views.report_pdf, name="report_pdf"),
    path("employees/<int:pk>/report/<str:month>/deduct/", views.report_deduction, name="report_deduction"),
    path("attendance/", views.attendance, name="attendance"),
    path("reports/", views.report_list, name="reports"),
    path("reports/<str:month>/excel/", views.report_excel, name="report_excel"),
    path("reports/<str:month>/reopen/", views.month_reopen, name="month_reopen"),
    path("reports/<str:month>/close/", views.month_close, name="month_close"),
    # The sales executives (and the Super Admin, for Site Visits)
    path("work/", views.work, name="work"),
    path("work/start/", views.work_start, name="work_start"),
    path("work/stop/", views.work_stop, name="work_stop"),
    path("work/complete/", views.work_complete, name="work_complete"),
    path("work/resume/", views.work_resume, name="work_resume"),
    path("site-visits/", views.status, name="status"),
]
