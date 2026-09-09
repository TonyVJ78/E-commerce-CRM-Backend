"""
Vistas del módulo de Tiendas.
Sprint 0 & CU10: Crear y listar tiendas del usuario autenticado, dashboard del vendedor.
"""

from datetime import timedelta
from django.db.models import F, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalogo.models import Producto, Variante
from apps.pedidos.models import ItemPedido, Pedido
from apps.usuarios.audit import AuditoriaCreateMixin
from apps.usuarios.permissions import IsEmpresaUser

from .models import Tienda
from .serializers import TiendaSerializer


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
