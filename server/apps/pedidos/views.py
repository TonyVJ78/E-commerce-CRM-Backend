from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalogo.models import Producto
from apps.usuarios.permissions import IsClienteUser

from .models import Carrito, HistorialEstadoPedido, ItemCarrito, ItemPedido, Pedido, Resena
from .serializers import (
    AgregarItemCarritoSerializer,
    CrearResenaSerializer,
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
    permission_classes = [permissions.IsAuthenticated, IsClienteUser]

    def get(self, request):
        pedidos = Pedido.objects.filter(cliente=request.user).order_by('-fecha')[:20]
        data = []
        for p in pedidos:
            items = []
            for it in p.items.select_related('variante__producto').all():
                subtot = float(it.cantidad) * float(it.precio_unitario)
                items.append({
                    'id': it.id,
                    'producto_id': it.variante.producto_id if it.variante_id else None,
                    'producto_nombre': it.variante.producto.nombre if it.variante and it.variante.producto else 'Producto',
                    'variante_nombre': it.variante.nombre if it.variante else 'Unica',
                    'cantidad': it.cantidad,
                    'precio_unitario': str(it.precio_unitario),
                    'subtotal': f"{subtot:.2f}",
                })
            data.append({
                'id': p.id,
                'tienda_id': p.tienda_id,
                'tienda_nombre': p.tienda.nombre if p.tienda else 'Tienda',
                'estado': p.estado_actual,
                'subtotal': str(p.subtotal),
                'total': str(p.total),
                'fecha': p.fecha.isoformat() if p.fecha else None,
                'items': items,
            })
        return Response({'pedidos': data}, status=status.HTTP_200_OK)


def _pedido_cliente(request, pedido_id):
    return get_object_or_404(
        Pedido.objects.select_related('tienda').prefetch_related(
            'items__variante__producto', 'historial_estados'
        ),
        pk=pedido_id,
        cliente=request.user,
    )


def _serializar_item_pedido(item):
    producto = item.variante.producto if item.variante_id else None
    return {
        'id': item.id,
        'producto_id': producto.id if producto else None,
        'producto_nombre': producto.nombre if producto else 'Producto',
        'variante_nombre': item.variante.nombre if item.variante_id else 'Unica',
        'cantidad': item.cantidad,
        'precio_unitario': str(item.precio_unitario),
        'subtotal': f'{item.cantidad * item.precio_unitario:.2f}',
    }


def _serializar_resena(resena):
    es_producto = resena.producto_id is not None
    return {
        'id': resena.id,
        'tipo': 'producto' if es_producto else 'tienda',
        'producto_id': resena.producto_id,
        'producto_nombre': resena.producto.nombre if es_producto else None,
        'tienda_id': resena.tienda_id,
        'tienda_nombre': resena.tienda.nombre,
        'calificacion': resena.calificacion,
        'comentario': resena.comentario,
        'fecha': resena.fecha.isoformat() if resena.fecha else None,
    }


class PedidoDetalleView(APIView):
    """GET /api/pedidos/mis-pedidos/<id>/ — Detalle y trazabilidad del pedido propio."""
    permission_classes = [permissions.IsAuthenticated, IsClienteUser]

    def get(self, request, pedido_id):
        pedido = _pedido_cliente(request, pedido_id)
        historial = HistorialEstadoPedido.objects.filter(pedido=pedido).order_by('fecha', 'pk')
        resenas = Resena.objects.filter(cliente=request.user, tienda=pedido.tienda).filter(
            producto__in=[item.variante.producto_id for item in pedido.items.all()]
        )
        resena_tienda = Resena.objects.filter(
            cliente=request.user, tienda=pedido.tienda, producto__isnull=True
        )

        return Response({
            'id': pedido.id,
            'tienda_id': pedido.tienda_id,
            'tienda_nombre': pedido.tienda.nombre,
            'estado': pedido.estado_actual,
            'subtotal': str(pedido.subtotal),
            'total': str(pedido.total),
            'fecha': pedido.fecha.isoformat() if pedido.fecha else None,
            'items': [_serializar_item_pedido(item) for item in pedido.items.all()],
            'historial': [{
                'estado': entrada.estado,
                'fecha': entrada.fecha.isoformat() if entrada.fecha else None,
                'observacion': entrada.observacion,
            } for entrada in historial],
            'resenas': [_serializar_resena(resena) for resena in resenas.select_related('producto', 'tienda')]
                + [_serializar_resena(resena) for resena in resena_tienda.select_related('tienda')],
        }, status=status.HTTP_200_OK)


class ResenasPedidoView(APIView):
    """GET/POST /api/pedidos/mis-pedidos/<id>/resenas/ — Consultar y registrar reseñas."""
    permission_classes = [permissions.IsAuthenticated, IsClienteUser]
    estados_calificables = {'completado', 'completada', 'entregado', 'finalizado', 'completed'}

    def get(self, request, pedido_id):
        pedido = _pedido_cliente(request, pedido_id)
        productos_ids = pedido.items.values_list('variante__producto_id', flat=True)
        producto_resenas = Resena.objects.filter(
            cliente=request.user, tienda=pedido.tienda, producto_id__in=productos_ids
        ).select_related('producto', 'tienda')
        tienda_resena = Resena.objects.filter(
            cliente=request.user, tienda=pedido.tienda, producto__isnull=True
        ).select_related('tienda')
        return Response(
            [_serializar_resena(resena) for resena in producto_resenas]
            + [_serializar_resena(resena) for resena in tienda_resena],
            status=status.HTTP_200_OK,
        )

    def post(self, request, pedido_id):
        pedido = _pedido_cliente(request, pedido_id)
        if pedido.estado_actual.strip().lower() not in self.estados_calificables:
            return Response(
                {'error': 'Solo se pueden calificar pedidos completados o entregados.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CrearResenaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        producto = None
        if values['tipo'] == 'producto':
            get_object_or_404(
                ItemPedido,
                pedido=pedido,
                variante__producto_id=values['producto_id'],
            )
            producto = get_object_or_404(Producto, pk=values['producto_id'])

        lookup = {
            'cliente': request.user,
            'tienda': pedido.tienda,
            'producto': producto,
        }
        resena = Resena.objects.filter(**lookup).first()
        created = resena is None
        if created:
            resena = Resena.objects.create(
                **lookup,
                calificacion=values['calificacion'],
                comentario=values['comentario'],
            )
        else:
            resena.calificacion = values['calificacion']
            resena.comentario = values['comentario']
            resena.save(update_fields=['calificacion', 'comentario'])

        return Response(
            _serializar_resena(resena),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


