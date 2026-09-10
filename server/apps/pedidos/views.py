from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.usuarios.permissions import IsClienteUser

from .models import Carrito, ItemCarrito, Pedido, ItemPedido
from .serializers import (
    AgregarItemCarritoSerializer,
    ItemCarritoCreadoSerializer,
    ItemCarritoDetalleSerializer,
    CarritoDetalleSerializer,
)



class AgregarItemCarritoView(APIView):
    """POST /api/pedidos/carrito/items/ — Agregar una variante al carrito."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = AgregarItemCarritoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save(cliente=request.user)
        response_serializer = ItemCarritoCreadoSerializer(item)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class CarritoDetalleView(APIView):
    """GET /api/pedidos/carrito/ — Obtener el carrito y sus items del cliente actual.
    DELETE /api/pedidos/carrito/ — Vaciar el carrito.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):

        carritos = Carrito.objects.filter(
            cliente=request.user
        ).prefetch_related('items__variante__producto', 'items__tienda')

        serializer = CarritoDetalleSerializer(carritos, many=True)
        total_global = sum(float(c['total']) for c in serializer.data)
        total_items = sum(c['cantidad_items'] for c in serializer.data)

        return Response({
            'carritos': serializer.data,
            'total_items': total_items,
            'total_global': f"{total_global:.2f}",
        }, status=status.HTTP_200_OK)

    def delete(self, request):
        ItemCarrito.objects.filter(carrito__cliente=request.user).delete()
        return Response({'mensaje': 'Carrito vaciado exitosamente.'}, status=status.HTTP_200_OK)


class ItemCarritoDetailView(APIView):
    """PATCH /api/pedidos/carrito/items/<int:item_id>/ — Cambiar cantidad.
    DELETE /api/pedidos/carrito/items/<int:item_id>/ — Eliminar ítem del carrito.
    """

    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, item_id):
        item = get_object_or_404(ItemCarrito, pk=item_id, carrito__cliente=request.user)
        cantidad = request.data.get('cantidad')

        if cantidad is None or int(cantidad) <= 0:
            item.delete()
            return Response({'mensaje': 'Item eliminado del carrito.'}, status=status.HTTP_200_OK)

        item.cantidad = int(cantidad)
        item.save()
        serializer = ItemCarritoDetalleSerializer(item)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, item_id):
        item = get_object_or_404(ItemCarrito, pk=item_id, carrito__cliente=request.user)
        item.delete()
        return Response({'mensaje': 'Item eliminado del carrito.'}, status=status.HTTP_200_OK)


class CheckoutView(APIView):
    """POST /api/pedidos/carrito/checkout/ — Procesa la compra de los carritos del cliente,
    generando Pedido e ItemPedido por cada tienda, activando los triggers de PostgreSQL
    que descuentan el stock y calculan totales.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        carritos = Carrito.objects.filter(
            cliente=request.user
        ).prefetch_related('items__variante')

        items_encontrados = False
        for c in carritos:
            if c.items.exists():
                items_encontrados = True
                break

        if not items_encontrados:
            return Response(
                {'error': 'El carrito de compras está vacío.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pedidos_creados = []
        items_comprados = []
        try:
            with transaction.atomic():
                for carrito in carritos:
                    items = list(carrito.items.select_related('variante').all())
                    if not items:
                        continue

                    # Crear pedido (los campos subtotal y total serán recalculados por el trigger de BD)
                    pedido = Pedido.objects.create(
                        cliente=request.user,
                        tienda=carrito.tienda,
                        estado_actual='completado',
                        subtotal=0,
                        total=0,
                    )

                    for item in items:
                        # Al insertar en item_pedido se dispara trg_actualizar_stock_item_pedido
                        # que descuenta variante.stock y verifica disponibilidad.
                        ItemPedido.objects.create(
                            tienda=carrito.tienda,
                            pedido=pedido,
                            variante=item.variante,
                            cantidad=item.cantidad,
                            precio_unitario=item.variante.precio,
                        )
                        items_comprados.append({
                            'variante_id': item.variante_id,
                            'producto_id': item.variante.producto_id,
                            'cantidad': item.cantidad,
                        })

                    # Vaciar items de este carrito
                    carrito.items.all().delete()
                    pedidos_creados.append(pedido.id)

        except Exception as exc:
            err_msg = str(exc)
            if 'Stock insuficiente' in err_msg:
                # Extraer mensaje conciso de la excepción lanzada por el trigger
                clean_msg = [line.strip() for line in err_msg.split('\n') if 'Stock insuficiente' in line]
                return Response(
                    {'error': clean_msg[0] if clean_msg else err_msg},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {'error': f'Error al procesar la compra: {err_msg}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                'mensaje': 'Compra realizada con éxito. Tu pedido ha sido procesado.',
                'pedidos': pedidos_creados,
                'items_comprados': items_comprados,
            },
            status=status.HTTP_201_CREATED,
        )


class MisPedidosView(APIView):
    """GET /api/pedidos/mis-pedidos/ — Listar los pedidos del usuario autenticado."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        pedidos = Pedido.objects.filter(cliente=request.user).order_by('-fecha')[:20]
        data = []
        for p in pedidos:
            items = []
            for it in p.items.select_related('variante__producto').all():
                subtot = float(it.cantidad) * float(it.precio_unitario)
                items.append({
                    'id': it.id,
                    'producto_nombre': it.variante.producto.nombre if it.variante and it.variante.producto else 'Producto',
                    'variante_nombre': it.variante.nombre if it.variante else 'Unica',
                    'cantidad': it.cantidad,
                    'precio_unitario': str(it.precio_unitario),
                    'subtotal': f"{subtot:.2f}",
                })
            data.append({
                'id': p.id,
                'tienda_nombre': p.tienda.nombre if p.tienda else 'Tienda',
                'estado': p.estado_actual,
                'total': str(p.total),
                'fecha': p.fecha.isoformat() if p.fecha else None,
                'items': items,
            })
        return Response({'pedidos': data}, status=status.HTTP_200_OK)


