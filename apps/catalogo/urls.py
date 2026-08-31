"""URLs del catálogo disponible para clientes."""

from django.urls import path

from . import views


urlpatterns = [
    path('tiendas/', views.TiendaCatalogoListView.as_view(), name='catalogo_tiendas'),
    path(
        'tiendas/<int:tienda_id>/productos/',
        views.ProductoTiendaListView.as_view(),
        name='catalogo_productos_tienda',
    ),
]
