"""Rutas de CU-14 para Web y Móvil."""

from django.urls import path

from . import views


urlpatterns = [
    path(
        'tiendas/<int:tienda_id>/',
        views.RecomendacionesTiendaView.as_view(),
        name='recomendaciones_tienda',
    ),
    path(
        'interacciones/',
        views.InteraccionProductoView.as_view(),
        name='recomendaciones_interaccion',
    ),
]
