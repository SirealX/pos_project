from django.urls import path

from . import views

app_name = 'staff'

urlpatterns = [
    path('shifts/', views.ShiftLogView.as_view(), name='shift-log'),
    path('schedule/', views.ScheduleListView.as_view(), name='schedule-list'),
    path('schedule/create/', views.ScheduleCreateView.as_view(), name='schedule-create'),
    path('schedule/<int:pk>/update/', views.ScheduleUpdateView.as_view(), name='schedule-update'),
    path('schedule/<int:pk>/delete/', views.ScheduleDeleteView.as_view(), name='schedule-delete'),
    path('force-clock-out/<int:user_id>/', views.force_clock_out, name='force-clock-out'),
]
