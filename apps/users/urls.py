from django.urls import path

from . import views

app_name = 'users'

urlpatterns = [
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),
    path('users/', views.UserListView.as_view(), name='list'),
    path('users/create/', views.UserCreateView.as_view(), name='create'),
    path('users/<int:pk>/update/', views.UserUpdateView.as_view(), name='update'),
    path('users/<int:pk>/delete/', views.UserDeleteView.as_view(), name='delete'),
]
