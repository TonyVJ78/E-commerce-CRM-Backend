"""URLs del catálogo disponible para clientes (CU-11)."""

from django.urls import path

from . import views


urlpatterns = [
    path('tiendas/', views.TiendaCatalogoListView.as_view(), name='catalogo_tiendas'),
    path('productos/', views.ProductoCatalogoGeneralListView.as_view(), name='catalogo_productos_general'),
    path('categorias/', views.CategoriaCatalogoListView.as_view(), name='catalogo_categorias'),
    path(
        'tiendas/<int:tienda_id>/productos/',
        views.ProductoTiendaListView.as_view(),
        name='catalogo_productos_tienda',
    ),
]

