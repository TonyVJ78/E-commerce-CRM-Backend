"""Rutas del Módulo de Inteligencia Artificial (CU-14) para Web y Móvil."""

from django.urls import path

from . import views


urlpatterns = [
    # Telemetría de interacción (acepta tanto 'eventos' como 'interacciones')
    path(
        'eventos/',
        views.InteraccionProductoView.as_view(),
        name='ia_eventos',
    ),
    path(
        'interacciones/',
        views.InteraccionProductoView.as_view(),
        name='ia_interacciones',
    ),

    # Recomendaciones personalizadas
    path(
        'recomendaciones/',
        views.RecomendacionesView.as_view(),
        name='ia_recomendaciones_query',
    ),
    path(
        'recomendaciones/tiendas/<int:tienda_id>/',
        views.RecomendacionesTiendaView.as_view(),
        name='ia_recomendaciones_tienda_prefijo',
    ),
    path(
        'tiendas/<int:tienda_id>/',
        views.RecomendacionesTiendaView.as_view(),
        name='ia_recomendaciones_tienda',
    ),
    path(
        'tiendas/<int:tienda_id>/compat/',
        views.RecomendacionesTiendaView.as_view(),
        name='recomendaciones_tienda',
    ),
]
