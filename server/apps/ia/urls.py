"""Rutas del Módulo de Inteligencia Artificial (CU-14) para Web y Móvil."""

from django.urls import path

from . import views, views_chatbot, views_informes


urlpatterns = [
    # Chatbot de recomendaciones con Claude
    path('chatbot/', views_chatbot.ChatbotView.as_view(), name='ia_chatbot'),

    # Informes de tienda con IA (CU-34)
    path('informes/', views_informes.InformeListView.as_view(), name='ia_informes'),
    path('informes/contexto/', views_informes.ContextoInformesView.as_view(), name='ia_informes_contexto'),
    path('informes/generar/', views_informes.GenerarInformeView.as_view(), name='ia_informes_generar'),
    path('informes/<int:pk>/', views_informes.InformeDetailView.as_view(), name='ia_informe_detalle'),
    path('informes/<int:pk>/exportar/', views_informes.ExportarInformeView.as_view(), name='ia_informe_exportar'),

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
    path(
        'interacciones/compat/',
        views.InteraccionProductoView.as_view(),
        name='recomendaciones_interaccion',
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
