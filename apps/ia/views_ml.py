"""Vistas de Machine Learning sobre los datos de una tienda.

Mismos permisos que los informes (módulo `informes` de la matriz CU-07): GET →
`informes.ver`, POST → `informes.crear`. La tienda debe ser una de las del
usuario; si no, 404.
"""

from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .informes_consultas import tiendas_permitidas
from .ml import datos as carga
from .ml.entrenamiento import MODULOS, entrenar_tienda
from .views_informes import PERMISOS_INFORMES


def _respuesta(tienda, omitidos: list[dict]) -> dict:
    guardados = {m.tipo: m for m in tienda.modelos_ml.all()}
    modelos = []
    for modulo in MODULOS:
        modelo = guardados.get(modulo.TIPO)
        if modelo is None:
            continue
        modelos.append({
            'tipo': modelo.tipo,
            'titulo': modulo.TITULO,
            'algoritmo': modelo.algoritmo,
            'entrenado_en': modelo.entrenado_en,
            'filas_entrenamiento': modelo.filas_entrenamiento,
            'metricas': modelo.metricas,
            'explicacion': modulo.EXPLICACION,
            'resultados': modelo.resultados,
        })
    return {
        'entrenado': bool(modelos),
        'dataset': carga.resumen_dataset(tienda),
        'modelos': modelos,
        'omitidos': omitidos,
    }


class ModelosMlView(APIView):
    """GET /api/ia/ml/tiendas/<tienda_id>/ — Dataset y modelos entrenados de la tienda."""

    permission_classes = PERMISOS_INFORMES

    def get(self, request, tienda_id):
        tienda = get_object_or_404(tiendas_permitidas(request.user), pk=tienda_id)
        return Response(_respuesta(tienda, []))


class EntrenarMlView(APIView):
    """POST /api/ia/ml/tiendas/<tienda_id>/entrenar/ — Reentrena los modelos y devuelve el resultado."""

    permission_classes = PERMISOS_INFORMES
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'informes'

    def post(self, request, tienda_id):
        tienda = get_object_or_404(tiendas_permitidas(request.user), pk=tienda_id)
        omitidos = entrenar_tienda(tienda)
        return Response(_respuesta(tienda, omitidos))
