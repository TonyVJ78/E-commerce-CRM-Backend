"""
URLs del módulo de Tiendas.
"""

from django.urls import include, path

from . import views

urlpatterns = [
    path('dashboard/', views.DashboardVendedorView.as_view(), name='dashboard_vendedor'),
    path(
        '<int:pk>/identidad/slug-disponible/',
        views.SlugDisponibilidadView.as_view(),
        name='tienda_slug_disponible',
    ),
    path(
        '<int:pk>/identidad/',
        views.TiendaIdentidadView.as_view(),
        name='tienda_identidad',
    ),
    path('', include('apps.catalogo.urls')),
    path('', views.TiendaListCreateView.as_view(), name='tienda_list_create'),
]

