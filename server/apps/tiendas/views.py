"""
Vistas del módulo de Tiendas.
Sprint 0 & CU10: Crear y listar tiendas del usuario autenticado, dashboard del vendedor.
"""

import logging
from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Sum
from django.db.models.functions import TruncDate
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import generics, permissions, status
from rest_framework.exceptions import APIException
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalogo.models import Producto, Variante
from apps.catalogo.services import CloudinaryConfigurationError, CloudinaryUploadError
from apps.pedidos.models import ItemPedido, Pedido
from apps.usuarios.audit import AuditoriaCreateMixin, AuditoriaUpdateMixin
from apps.usuarios.permissions import IsEmpresaUser

from .models import Tienda
from .serializers import TiendaIdentidadSerializer, TiendaSerializer


logger = logging.getLogger(__name__)


class ControlledErrorMixin:
    """Conserva errores DRF esperados y oculta detalles de fallos inesperados."""

    def handle_exception(self, exc):
        if isinstance(exc, (APIException, Http404, PermissionDenied)):
            return super().handle_exception(exc)
        logger.exception('Error inesperado en el endpoint de identidad de marca')
        return Response(
            {'detail': 'No se pudo procesar la identidad de marca.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class TiendaListCreateView(AuditoriaCreateMixin, generics.ListCreateAPIView):
    """
    GET  /api/tiendas/ — Listar tiendas del usuario autenticado (solo rol empresa).
    POST /api/tiendas/ — Crear nueva tienda (asociada al usuario como propietario).
    """
    serializer_class = TiendaSerializer
    permission_classes = [permissions.IsAuthenticated, IsEmpresaUser]
    audit_tabla = 'tienda'

    def get_queryset(self):
        return Tienda.objects.filter(propietario=self.request.user)

    def get_auditoria_extra_save_kwargs(self):
        return {'propietario': self.request.user}


class TiendaIdentidadView(
    ControlledErrorMixin,
    AuditoriaUpdateMixin,
    generics.RetrieveUpdateAPIView,
):
    """GET/PATCH de identidad, siempre resuelto dentro del tenant autenticado."""

    serializer_class = TiendaIdentidadSerializer
    permission_classes = [permissions.IsAuthenticated, IsEmpresaUser]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ['get', 'patch', 'head', 'options']
    audit_tabla = 'tienda'

    def get_queryset(self):
        return Tienda.objects.filter(propietario=self.request.user)

    @transaction.atomic
    def perform_update(self, serializer):
        super().perform_update(serializer)

    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except (CloudinaryConfigurationError, CloudinaryUploadError) as exc:
            return Response(
                {'logo': [str(exc)]},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class SlugDisponibilidadView(ControlledErrorMixin, APIView):
    """Comprueba disponibilidad sin sustituir la validación del PATCH."""

    permission_classes = [permissions.IsAuthenticated, IsEmpresaUser]

    def get(self, request, pk):
        tienda = get_object_or_404(
            Tienda,
            pk=pk,
            propietario=request.user,
        )
        slug = slugify(request.query_params.get('slug', ''))
        if not slug:
            return Response(
                {'slug': ['Ingresa un slug válido.']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(slug) > 100:
            return Response(
                {'slug': ['El slug no puede superar los 100 caracteres.']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        disponible = not Tienda.objects.filter(slug=slug).exclude(pk=tienda.pk).exists()
        return Response({'slug': slug, 'disponible': disponible})


class DashboardVendedorView(APIView):
    """
    GET /api/tiendas/dashboard/ — Obtener métricas y KPIs para el Panel del Vendedor (CU10).
    """
    permission_classes = [permissions.IsAuthenticated, IsEmpresaUser]

    def get(self, request):
        user = request.user

        # 1. Métricas de Productos
        productos = Producto.objects.filter(tienda__propietario=user)
        total_productos = productos.count()
        productos_activos = productos.filter(activo=True).count()

        # 2. Métricas de Pedidos
        pedidos = Pedido.objects.filter(tienda__propietario=user)
        total_pedidos = pedidos.count()
        pedidos_pendientes = pedidos.filter(estado_actual='pendiente').count()

        # 3. Ingresos (Suma de pedidos que no estén cancelados)
        ingresos_totales = pedidos.exclude(estado_actual='cancelado').aggregate(
            suma=Sum('total')
        )['suma'] or 0.00

        # 4. Variantes bajo stock (stock <= stock_minimo)
        productos_bajo_stock = Variante.objects.filter(
            producto__tienda__propietario=user,
            activa=True,
            stock__lte=F('stock_minimo')
        ).count()

        # 5. Ventas últimos 7 días optimizadas en una única consulta agrupada (sin N+1)
        hoy = timezone.now().date()
        inicio_semana = hoy - timedelta(days=6)

        ventas_agrupadas = (
            ItemPedido.objects.filter(
                pedido__tienda__propietario=user,
                pedido__fecha__date__gte=inicio_semana,
                pedido__fecha__date__lte=hoy,
            )
            .exclude(pedido__estado_actual='cancelado')
            .annotate(dia=TruncDate('pedido__fecha'))
            .values('dia')
            .annotate(total_vendidos=Sum('cantidad'))
        )
        ventas_por_dia = {item['dia']: item['total_vendidos'] or 0 for item in ventas_agrupadas}

        ventas_semana = [
            {
                'fecha': (inicio_semana + timedelta(days=i)).strftime('%d/%m'),
                'cantidad': ventas_por_dia.get(inicio_semana + timedelta(days=i), 0)
            }
            for i in range(7)
        ]

        return Response({
            'total_productos': total_productos,
            'productos_activos': productos_activos,
            'total_pedidos': total_pedidos,
            'pedidos_pendientes': pedidos_pendientes,
            'ingresos_totales': float(ingresos_totales),
            'productos_bajo_stock': productos_bajo_stock,
            'grafico_ventas': ventas_semana,
        })
