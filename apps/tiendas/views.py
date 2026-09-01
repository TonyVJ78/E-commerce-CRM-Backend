"""
Vistas del módulo de Tiendas.
Sprint 0: Crear y listar tiendas del usuario autenticado.
"""

from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Sum, F

from apps.catalogo.models import Producto, Inventario
from apps.pedidos.models import Pedido

from apps.usuarios.audit import AuditoriaCreateMixin

from .models import Tienda
from .serializers import TiendaSerializer


class IsEmpresaUser(permissions.BasePermission):
    """Permiso que permite acceso únicamente a usuarios con rol 'empresa'."""
    message = "Solo los usuarios con rol 'empresa' pueden crear o administrar tiendas."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.rol
            and request.user.rol.nombre == 'empresa'
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
        
        # 4. Inventario bajo stock (stock <= umbral_minimo)
        productos_bajo_stock = Inventario.objects.filter(
            tienda__propietario=user,
            stock__lte=F('umbral_minimo')
        ).count()
        
        # 5. Datos para gráfico (últimos 7 días de cantidad de productos vendidos)
        from django.utils import timezone
        from datetime import timedelta
        from apps.pedidos.models import ItemPedido
        
        hoy = timezone.now().date()
        ventas_semana = []
        # Calcular los últimos 7 días empezando desde hace 6 días hasta hoy
        for i in range(6, -1, -1):
            dia = hoy - timedelta(days=i)
            # Sumar la cantidad de items de pedidos en ese día que no estén cancelados
            items = ItemPedido.objects.filter(
                pedido__tienda__propietario=user,
                pedido__fecha__date=dia
            ).exclude(pedido__estado_actual='cancelado').aggregate(
                total_vendidos=Sum('cantidad')
            )['total_vendidos']
            
            ventas_semana.append({
                'fecha': dia.strftime('%d/%m'),
                'cantidad': items or 0
            })

        return Response({
            'total_productos': total_productos,
            'productos_activos': productos_activos,
            'total_pedidos': total_pedidos,
            'pedidos_pendientes': pedidos_pendientes,
            'ingresos_totales': float(ingresos_totales),
            'productos_bajo_stock': productos_bajo_stock,
            'grafico_ventas': ventas_semana,
        })
