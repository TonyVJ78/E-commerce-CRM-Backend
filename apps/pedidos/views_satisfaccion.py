"""
Panel de satisfacción de clientes de una tienda de la empresa.

Exige el módulo `pedidos` de la matriz de permisos (CU-07), igual que la gestión
de pedidos: GET -> `pedidos.ver`, POST (resumen con IA) -> `pedidos.crear`. Toda
consulta parte de una tienda del usuario autenticado.
"""

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from . import satisfaccion, satisfaccion_ia
from .serializers_satisfaccion import FiltroSatisfaccionSerializer
from .views_empresa import PedidosTiendaMixin

logger = logging.getLogger(__name__)


class ResumenIaThrottle(UserRateThrottle):
    scope = 'resumen_satisfaccion'
    rate = '10/min'


class SatisfaccionTiendaView(PedidosTiendaMixin, APIView):
    """GET /api/tiendas/<tienda_id>/satisfaccion/?desde=&hasta=&min_resenas="""

    def get(self, request, tienda_id):
        tienda = self.get_tienda()
        filtro = FiltroSatisfaccionSerializer(data=request.query_params)
        filtro.is_valid(raise_exception=True)
        datos = filtro.validated_data
        return Response({
            'tienda': {'id': tienda.id, 'nombre': tienda.nombre},
            'desde': datos.get('desde'),
            'hasta': datos.get('hasta'),
            **satisfaccion.panel(
                tienda, datos.get('desde'), datos.get('hasta'), datos['min_resenas'],
            ),
        })


class ResumenComentariosIaView(PedidosTiendaMixin, APIView):
    """POST /api/tiendas/<tienda_id>/satisfaccion/resumen-ia/ con `desde`/`hasta` opcionales."""

    throttle_classes = [ResumenIaThrottle]

    def post(self, request, tienda_id):
        tienda = self.get_tienda()
        filtro = FiltroSatisfaccionSerializer(data=request.data)
        filtro.is_valid(raise_exception=True)
        datos = filtro.validated_data

        resenas = satisfaccion.resenas_en_rango(tienda, datos.get('desde'), datos.get('hasta'))
        comentarios = satisfaccion.ultimas_resenas_con_comentario(
            resenas, satisfaccion_ia.MAX_COMENTARIOS,
        )
        if not comentarios:
            return Response(
                {'detail': 'No hay comentarios en este periodo para resumir.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            resumen = satisfaccion_ia.resumir_comentarios(tienda.nombre, comentarios)
        except satisfaccion_ia.ResumenNoConfigurado as exc:
            logger.error('Resumen de satisfacción sin configurar: %s', exc)
            return Response(
                {'detail': 'El asistente no está disponible en este momento.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except satisfaccion_ia.ResumenNoDisponible as exc:
            logger.warning('Resumen de satisfacción no disponible: %s', exc.__cause__ or exc)
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(resumen)
