from django.urls import path

from . import views

app_name = 'sales'

urlpatterns = [
    path('', views.pos_view, name='pos'),
    path('cart/add/<int:product_id>/', views.cart_add, name='cart-add'),
    path('cart/remove/<int:product_id>/', views.cart_remove, name='cart-remove'),
    path('cart/set/<int:product_id>/', views.cart_set_quantity, name='cart-set-quantity'),
    path('checkout/', views.checkout, name='checkout'),
    path('sales/', views.SaleListView.as_view(), name='sale-list'),
    path('sales/<int:pk>/', views.SaleDetailView.as_view(), name='sale-detail'),
    path('sales/<int:pk>/void/', views.SaleVoidView.as_view(), name='sale-void'),
]
