"""Panel de KPIs de las tiendas y su interpretación con IA.

Mismos permisos que el resto de informes (módulo `informes`: GET → ver, POST →
crear) y mismo alcance por tienda (`tiendas_permitidas`).
"""

import logging

from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import informes, panel_interpretacion, panel_kpis
from .informes_consultas import tiendas_permitidas
from .serializers_panel import InterpretarPanelSerializer, PanelSerializer
from .views_informes import PERMISOS_INFORMES


logger = logging.getLogger(__name__)


def _calcular_panel(usuario, filtros):
    tiendas = list(tiendas_permitidas(usuario).order_by('nombre').values('id', 'nombre'))
    tienda_id = filtros.get('tienda')
    if tienda_id and tienda_id not in {t['id'] for t in tiendas}:
        raise NotFound('No existe esa tienda o no tienes acceso a ella.')
    return panel_kpis.calcular(tiendas, tienda_id, filtros['desde'], filtros['hasta'], filtros['comparar_con'])


class PanelView(APIView):
    """GET /api/ia/informes/panel/ — KPIs de la tienda con su comparación y las series para los gráficos."""

    permission_classes = PERMISOS_INFORMES

    def get(self, request):
        serializer = PanelSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return Response(_calcular_panel(request.user, serializer.validated_data))


class InterpretarPanelView(APIView):
    """POST /api/ia/informes/panel/interpretar/ — Explica el panel con IA.

    Recibe los mismos filtros del panel más una `pregunta` opcional y devuelve
    `{"resumen", "hallazgos", "alertas", "recomendaciones"}`.
    """

    permission_classes = PERMISOS_INFORMES
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'informes'

    def post(self, request):
        serializer = InterpretarPanelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        filtros = serializer.validated_data
        panel = _calcular_panel(request.user, filtros)

        try:
            return Response(panel_interpretacion.interpretar(panel, filtros.get('pregunta', '')))
        except informes.InformesNoConfigurado as exc:
            logger.error('Interpretación del panel sin configurar: %s', exc)
            return Response(
                {'detail': 'El asistente de informes no está disponible en este momento.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except informes.InformesNoDisponible as exc:
            logger.warning('Interpretación del panel no disponible: %s', exc.__cause__ or exc)
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        except panel_interpretacion.InterpretacionRechazada as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
