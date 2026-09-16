from decimal import Decimal

import stripe
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Carrito, ItemCarrito, MetodoPago, Pago, Pedido, ItemPedido
from .serializers import (
    AgregarItemCarritoSerializer,
    ItemCarritoCreadoSerializer,
    ItemCarritoDetalleSerializer,
    CarritoDetalleSerializer,
)

NOMBRE_METODO_STRIPE = 'Tarjeta (Stripe)'
NOMBRE_METODO_EFECTIVO = 'Efectivo'


def _total_carrito_bs(carritos):
    """Suma en Bs de todos los ítems de todos los carritos del cliente."""
    total = Decimal('0')
    for carrito in carritos:
        for item in carrito.items.all():
            total += item.cantidad * item.variante.precio
    return total


def _usd_centavos(total_bs):
    """Convierte un monto en Bs a centavos de USD según STRIPE_USD_BOB_RATE."""
    tasa = Decimal(str(settings.STRIPE_USD_BOB_RATE))
    return round((total_bs / tasa) * 100)



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


class IniciarPagoStripeView(APIView):
    """POST /api/pedidos/carrito/pago-intento/ — Crea el PaymentIntent de Stripe
    para el total actual del carrito del cliente (CU-19). El cliente confirma el
    pago en el propio formulario (Stripe Elements / CardField) usando el
    `client_secret` devuelto; recién con ese pago confirmado, CheckoutView genera
    el pedido.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        carritos = Carrito.objects.filter(
            cliente=request.user
        ).prefetch_related('items__variante')

        total_bs = _total_carrito_bs(carritos)
        if total_bs <= 0:
            return Response(
                {'error': 'El carrito de compras está vacío.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        monto_usd_centavos = _usd_centavos(total_bs)

        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            intent = stripe.PaymentIntent.create(
                amount=monto_usd_centavos,
                currency='usd',
                # allow_redirects='never' asegura que confirmPayment() en el
                # frontend resuelva sin navegar a otra página: solo se ofrecen
                # métodos que se pueden confirmar dentro del propio formulario.
                automatic_payment_methods={'enabled': True, 'allow_redirects': 'never'},
                metadata={
                    'cliente_id': str(request.user.id),
                    'cliente_email': request.user.email,
                    'total_bs': str(total_bs),
                },
            )
        except stripe.error.StripeError as exc:
            return Response(
                {'error': f'No se pudo iniciar el pago con Stripe: {exc.user_message or str(exc)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                'client_secret': intent.client_secret,
                'payment_intent_id': intent.id,
                'publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
                'monto_bs': str(total_bs),
                'monto_usd': f'{monto_usd_centavos / 100:.2f}',
            },
            status=status.HTTP_200_OK,
        )


class CheckoutView(APIView):
    """POST /api/pedidos/carrito/checkout/ — Procesa la compra de los carritos del cliente,
    generando Pedido e ItemPedido por cada tienda, activando los triggers de PostgreSQL
    que descuentan el stock y calculan totales. Registra además el Pago (CU-19):
    con `metodo_pago: "stripe"` exige un `payment_intent_id` ya confirmado y cuyo
    monto coincida con el carrito; con cualquier otro valor (efectivo, QR) el pago
    queda `pendiente` (se cobra contra entrega), como hasta ahora.
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

        metodo_pago_valor = str(request.data.get('metodo_pago') or NOMBRE_METODO_EFECTIVO).strip()
        es_stripe = metodo_pago_valor.lower() == 'stripe'
        payment_intent_id = str(request.data.get('payment_intent_id') or '').strip()

        if es_stripe:
            if not payment_intent_id:
                return Response(
                    {'error': 'Falta el identificador del pago con tarjeta.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            stripe.api_key = settings.STRIPE_SECRET_KEY
            try:
                intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            except stripe.error.StripeError as exc:
                return Response(
                    {'error': f'No se pudo verificar el pago con Stripe: {exc.user_message or str(exc)}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if intent.status != 'succeeded':
                return Response(
                    {'error': 'El pago con tarjeta todavía no se completó.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            total_bs_actual = _total_carrito_bs(carritos)
            monto_esperado = _usd_centavos(total_bs_actual)
            # Tolerancia de 1 centavo de USD por redondeo entre el intento y el
            # recálculo del carrito.
            if abs(intent.amount - monto_esperado) > 1:
                return Response(
                    {'error': 'El monto pagado no coincide con el total actual del carrito.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            metodo_pago_nombre = NOMBRE_METODO_STRIPE
        elif metodo_pago_valor.lower() == 'qr':
            metodo_pago_nombre = 'QR'
        elif metodo_pago_valor.lower() in ('efectivo', ''):
            metodo_pago_nombre = NOMBRE_METODO_EFECTIVO
        else:
            # Etiquetas propias (p.ej. las del móvil, "QR Simple (Bolivia)") se
            # respetan tal cual en vez de forzarlas a un nombre semilla.
            metodo_pago_nombre = metodo_pago_valor

        metodo_pago_obj, _ = MetodoPago.objects.get_or_create(nombre=metodo_pago_nombre)

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

                    # El trigger fn_recalcular_total_pedido ya fijó pedido.total; se
                    # recarga para que el Pago quede con el monto real cobrado.
                    pedido.refresh_from_db()
                    Pago.objects.create(
                        tienda=carrito.tienda,
                        pedido=pedido,
                        metodo_pago=metodo_pago_obj,
                        monto=pedido.total,
                        estado='pagado' if es_stripe else 'pendiente',
                        referencia_transaccion=payment_intent_id if es_stripe else '',
                    )
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
                'metodo_pago': metodo_pago_nombre,
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


