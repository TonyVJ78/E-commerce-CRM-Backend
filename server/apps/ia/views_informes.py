"""Vistas de los informes de tienda con IA (CU-34).

Todas exigen el módulo `informes` de la matriz de permisos (CU-07): GET →
`informes.ver`, POST → `informes.crear`, DELETE → `informes.eliminar`. Además,
los datos se limitan a las tiendas del usuario (`tiendas_permitidas`) y cada
quien ve solo los informes que generó.
"""

import logging

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.usuarios.permissions import PermisoModulo, usuario_tiene_permiso

from . import informes, informes_exportar
from .informes_consultas import es_administrador, tiendas_permitidas
from .models import ReporteGenerado
from .serializers_informes import GenerarInformeSerializer, InformeResumenSerializer, InformeSerializer


logger = logging.getLogger(__name__)

PERMISOS_INFORMES = [permissions.IsAuthenticated, PermisoModulo('informes')]

EJEMPLOS = [
    'Productos más vendidos de los últimos 30 días',
    'Ventas por semana de este mes',
    'Productos con stock bajo',
    'Mejores clientes por monto comprado',
    'Pedidos por estado',
    'Lo más buscado por los clientes',
]


def _informes_del_usuario(usuario):
    return (ReporteGenerado.objects
            .filter(generado_por_usuario=usuario, tipo_reporte=informes.TIPO_REPORTE)
            .select_related('tienda', 'generado_por_usuario'))


class ContextoInformesView(APIView):
    """GET /api/ia/informes/contexto/ — Tiendas disponibles y qué puede hacer el usuario."""

    permission_classes = PERMISOS_INFORMES

    def get(self, request):
        tiendas = tiendas_permitidas(request.user).order_by('nombre').values('id', 'nombre')
        return Response({
            'tiendas': list(tiendas),
            'es_administrador': es_administrador(request.user),
            'puede_crear': usuario_tiene_permiso(request.user, 'informes.crear'),
            'puede_eliminar': usuario_tiene_permiso(request.user, 'informes.eliminar'),
            'ejemplos': EJEMPLOS,
        })


class GenerarInformeView(APIView):
    """POST /api/ia/informes/generar/ — Un turno de la conversación de informes.

    Recibe `{"mensajes": [{"rol", "contenido"}, ...], "tienda_id": <opcional>}`
    y devuelve `{"tipo": "pregunta"|"informe", "mensaje", "sugerencias", "informe"}`.
    """

    permission_classes = PERMISOS_INFORMES
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'informes'

    def post(self, request):
        serializer = GenerarInformeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tienda = None
        tienda_id = serializer.validated_data.get('tienda_id')
        if tienda_id:
            tienda = tiendas_permitidas(request.user).filter(pk=tienda_id).first()
            if tienda is None:
                return Response({'detail': 'No tienes acceso a esa tienda.'}, status=status.HTTP_403_FORBIDDEN)
        elif not tiendas_permitidas(request.user).exists():
            return Response(
                {'detail': 'No tienes tiendas asignadas para generar informes.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            resultado = informes.generar(request.user, serializer.como_mensajes_claude(), tienda)
        except informes.InformesNoConfigurado as exc:
            logger.error('Informes IA sin configurar: %s', exc)
            return Response(
                {'detail': 'El asistente de informes no está disponible en este momento.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except informes.InformesNoDisponible as exc:
            logger.warning('Informes IA no disponible: %s', exc.__cause__ or exc)
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        informe = resultado['informe']
        return Response({
            'tipo': resultado['tipo'],
            'mensaje': resultado['mensaje'],
            'sugerencias': resultado['sugerencias'],
            'informe': InformeSerializer(informe).data if informe else None,
        })


class InformeListView(generics.ListAPIView):
    """GET /api/ia/informes/ — Historial de informes del usuario (los 50 más recientes)."""

    permission_classes = PERMISOS_INFORMES
    serializer_class = InformeResumenSerializer
    pagination_class = None

    def get_queryset(self):
        return _informes_del_usuario(self.request.user)[:50]


class InformeDetailView(generics.RetrieveDestroyAPIView):
    """GET/DELETE /api/ia/informes/<id>/ — Ver o borrar un informe propio."""

    permission_classes = PERMISOS_INFORMES
    serializer_class = InformeSerializer

    def get_queryset(self):
        return _informes_del_usuario(self.request.user)


class ExportarInformeView(APIView):
    """GET /api/ia/informes/<id>/exportar/?formato=pdf|xlsx — Descarga el informe."""

    permission_classes = PERMISOS_INFORMES

    TIPOS = {
        'pdf': ('application/pdf', informes_exportar.generar_pdf),
        'xlsx': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                 informes_exportar.generar_xlsx),
    }

    def get(self, request, pk):
        formato = (request.query_params.get('formato') or 'pdf').lower()
        if formato == 'excel':
            formato = 'xlsx'
        if formato not in self.TIPOS:
            return Response({'detail': 'Formato no soportado. Usa pdf o xlsx.'}, status=status.HTTP_400_BAD_REQUEST)

        informe = get_object_or_404(_informes_del_usuario(request.user), pk=pk)
        tipo_contenido, generar = self.TIPOS[formato]
        respuesta = HttpResponse(generar(informe), content_type=tipo_contenido)
        nombre = informes_exportar.nombre_archivo(informe, formato)
        respuesta['Content-Disposition'] = f'attachment; filename="{nombre}"'
        respuesta['Access-Control-Expose-Headers'] = 'Content-Disposition'
        return respuesta
