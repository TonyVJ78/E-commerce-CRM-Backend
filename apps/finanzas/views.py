import hmac
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tiendas.models import Tienda
from apps.usuarios.audit import (
    ACCION_ACTUALIZAR,
    ACCION_CREAR,
    ACCION_ELIMINAR,
    registrar_auditoria,
    snapshot_instancia,
)
from apps.usuarios.permissions import IsEmpresa

from .brl import brl_habilitado, estado_brl
from .models import GastoOperativo, TipoCambio
from .serializers import GastoFiltroSerializer, GastoOperativoSerializer, TipoCambioSerializer
from .tipo_cambio import actualizar_tipo_cambio, tipo_cambio_vigente

DIAS_HISTORIAL_PUBLICO = 30


class TipoCambioView(APIView):
    """GET /api/finanzas/tipo-cambio/ — cotización vigente y los últimos 30 días."""
    permission_classes = [permissions.AllowAny]
    # Es pública: un token vencido en el navegador no debe convertirla en un 401.
    authentication_classes = []

    def get(self, request):
        vigente = tipo_cambio_vigente()
        extra = {'brl': estado_brl()} if brl_habilitado() else {}
        if vigente is None:
            return Response({'vigente': None, 'historial': [], **extra})
        historial = TipoCambio.objects.filter(fecha__lte=vigente.fecha)[:DIAS_HISTORIAL_PUBLICO]
        return Response({
            'vigente': TipoCambioSerializer(vigente).data,
            'historial': TipoCambioSerializer(historial, many=True).data,
            **extra,
        })


class ActualizarTipoCambioView(APIView):
    """GET /api/finanzas/tipo-cambio/actualizar/ — lo llama Vercel Cron con `Bearer <CRON_SECRET>`."""
    permission_classes = [permissions.AllowAny]
    # El token del cron no es un JWT: sin esto JWTAuthentication lo rechazaría antes de llegar aquí.
    authentication_classes = []

    def get(self, request):
        if not settings.CRON_SECRET:
            return Response(
                {'error': 'CRON_SECRET no está configurado en el servidor.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        esperado = f'Bearer {settings.CRON_SECRET}'
        recibido = request.headers.get('Authorization', '')
        if not hmac.compare_digest(recibido.encode(), esperado.encode()):
            return Response({'error': 'No autorizado.'}, status=status.HTTP_401_UNAUTHORIZED)

        guardadas = actualizar_tipo_cambio()
        if guardadas is None:
            return Response(
                {'error': 'No se pudo consultar el tipo de cambio; se mantiene la última cotización guardada.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        vigente = tipo_cambio_vigente()
        return Response({
            'guardadas': guardadas,
            'vigente': TipoCambioSerializer(vigente).data if vigente else None,
        })


class GastosTiendaMixin:
    permission_classes = [permissions.IsAuthenticated, IsEmpresa]

    def get_tienda(self):
        return get_object_or_404(
            Tienda,
            pk=self.kwargs['tienda_id'],
            propietario=self.request.user,
        )

    def get_queryset(self):
        return GastoOperativo.objects.filter(tienda=self.get_tienda())

    def gastos_filtrados(self):
        filtros = GastoFiltroSerializer(data=self.request.query_params)
        filtros.is_valid(raise_exception=True)
        datos = filtros.validated_data
        gastos = self.get_queryset()
        if 'desde' in datos:
            gastos = gastos.filter(fecha__gte=datos['desde'])
        if 'hasta' in datos:
            gastos = gastos.filter(fecha__lte=datos['hasta'])
        if 'categoria' in datos:
            gastos = gastos.filter(categoria=datos['categoria'])
        return gastos


class GastoListCreateView(GastosTiendaMixin, generics.ListCreateAPIView):
    """GET/POST /api/finanzas/tiendas/<tienda_id>/gastos/?desde=&hasta=&categoria="""
    serializer_class = GastoOperativoSerializer

    def list(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.gastos_filtrados(), many=True).data)

    def perform_create(self, serializer):
        gasto = serializer.save(tienda=self.get_tienda(), registrado_por=self.request.user)
        registrar_auditoria(
            self.request, ACCION_CREAR, tabla='gasto_operativo', registro_id=gasto.pk,
            datos_nuevos=snapshot_instancia(gasto),
        )


class GastoDetailView(GastosTiendaMixin, generics.RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE /api/finanzas/tiendas/<tienda_id>/gastos/<pk>/"""
    serializer_class = GastoOperativoSerializer

    def perform_update(self, serializer):
        anterior = snapshot_instancia(serializer.instance)
        gasto = serializer.save()
        registrar_auditoria(
            self.request, ACCION_ACTUALIZAR, tabla='gasto_operativo', registro_id=gasto.pk,
            datos_anteriores=anterior, datos_nuevos=snapshot_instancia(gasto),
        )

    def perform_destroy(self, instance):
        pk, anterior = instance.pk, snapshot_instancia(instance)
        instance.delete()
        registrar_auditoria(
            self.request, ACCION_ELIMINAR, tabla='gasto_operativo', registro_id=pk,
            datos_anteriores=anterior,
        )


class GastoTotalesView(GastosTiendaMixin, APIView):
    """GET /api/finanzas/tiendas/<tienda_id>/gastos/totales/ — total, por categoría y por mes (mismos filtros)."""

    def get(self, request, tienda_id):
        gastos = self.gastos_filtrados()
        por_categoria = {
            fila['categoria']: fila['total']
            for fila in gastos.order_by().values('categoria').annotate(total=Sum('monto'))
        }
        por_mes = (
            gastos.order_by().annotate(mes=TruncMonth('fecha')).values('mes')
            .annotate(total=Sum('monto')).order_by('mes')
        )
        return Response({
            'total': sum(por_categoria.values(), Decimal('0.00')),
            'por_categoria': [
                {'categoria': valor, 'etiqueta': etiqueta, 'total': por_categoria[valor]}
                for valor, etiqueta in GastoOperativo.Categoria.choices
                if valor in por_categoria
            ],
            'por_mes': [{'mes': fila['mes'].strftime('%Y-%m'), 'total': fila['total']} for fila in por_mes],
        })
