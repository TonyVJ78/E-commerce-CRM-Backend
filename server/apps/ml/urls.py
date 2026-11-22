"""Rutas de CU-35: Machine Learning.

Prefijo: /api/ml/
"""

from django.urls import path

from . import views

urlpatterns = [
    # Pronóstico de ventas
    path(
        'ventas/pronosticar/',
        views.PronosticarVentasView.as_view(),
        name='ml_ventas_pronosticar',
    ),
    path(
        'ventas/pronosticos/',
        views.ListarPronosticosVentaView.as_view(),
        name='ml_ventas_listar',
    ),

    # Riesgo de abandono
    path(
        'clientes/riesgo-abandono/',
        views.EvaluarRiesgoAbandonoView.as_view(),
        name='ml_abandono_evaluar',
    ),
    path(
        'clientes/riesgos-abandono/',
        views.ListarRiesgosAbandonoView.as_view(),
        name='ml_abandono_listar',
    ),

    # Predicción de compras
    path(
        'compras/predecir/',
        views.PredecirCompraView.as_view(),
        name='ml_compras_predecir',
    ),
    path(
        'compras/predicciones/',
        views.ListarPrediccionesCompraView.as_view(),
        name='ml_compras_listar',
    ),

    # Entrenamientos
    path(
        'entrenamientos/',
        views.ListarEntrenamientosView.as_view(),
        name='ml_entrenamientos_listar',
    ),
]
