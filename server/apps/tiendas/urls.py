"""
URLs del módulo de Tiendas y Productos.
"""

from django.urls import path

from . import views

urlpatterns = [
    path('', views.TiendaListCreateView.as_view(), name='tienda_list_create'),
    path('productos/', views.ProductoListCreateView.as_view(), name='producto_list_create'),
    path('productos/<int:pk>/', views.ProductoDetailView.as_view(), name='producto_detail'),
]