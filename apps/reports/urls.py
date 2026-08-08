from django.urls import path

from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('sales/', views.SalesReportView.as_view(), name='sales-report'),
    path('sales/export/', views.sales_report_csv, name='sales-report-csv'),
    path('staff-hours/', views.StaffHoursReportView.as_view(), name='staff-hours'),
    path('staff-hours/export/', views.staff_hours_csv, name='staff-hours-csv'),
]
