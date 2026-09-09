"""
URLs del módulo de Tiendas.
"""

from django.urls import path

from . import views

urlpatterns = [
    path('dashboard/', views.DashboardVendedorView.as_view(), name='dashboard_vendedor'),
    path('', views.TiendaListCreateView.as_view(), name='tienda_list_create'),
]
