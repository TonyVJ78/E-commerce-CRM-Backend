from decimal import Decimal, ROUND_HALF_UP

import stripe
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalogo.models import Producto
from apps.usuarios.permissions import IsClienteUser
from . import estados
from .models import Carrito, HistorialEstadoPedido, ItemCarrito, ItemPedido, MetodoPago, Pago, Pedido, Resena
from .presentacion import envio_a_dict, historial_a_dict
from .serializers import (
    AgregarItemCarritoSerializer,
    CrearResenaSerializer,
    ItemCarritoCreadoSerializer,
    ItemCarritoDetalleSerializer,
    CarritoDetalleSerializer,
)

NOMBRE_METODO_STRIPE = 'Tarjeta (Stripe)'
NOMBRE_METODO_EFECTIVO = 'Efectivo'
NOMBRE_METODO_QR = 'QR'


def _total_carrito_bs(carritos):
    """Suma en Bs de todos los ítems de todos los carritos del cliente."""
    total = Decimal('0.00')
    for carrito in carritos:
        for item in carrito.items.all():
            total += Decimal(str(item.cantidad)) * Decimal(str(item.variante.precio))
    return total


def _usd_centavos(total_bs: Decimal) -> int:
    """Convierte un monto en Bs a centavos de USD según STRIPE_USD_BOB_RATE con redondeo estándar."""
    tasa = Decimal(str(getattr(settings, 'STRIPE_USD_BOB_RATE', 6.96)))
    if tasa <= Decimal('0'):
        tasa = Decimal('6.96')
    monto_usd = (total_bs / tasa).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return int(monto_usd * 100)


class AgregarItemCarritoView(APIView):
    """POST /api/pedidos/carrito/items/ — Agregar una variante al carrito."""

    permission_classes = [permissions.IsAuthenticated, IsClienteUser]

    def post(self, request):
        serializer = AgregarItemCarritoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save(cliente=request.user)

        try:
            from apps.ia.models import EventoUsuario
            from apps.ia.services import registrar_interaccion

            registrar_interaccion(
                cliente=request.user,
                tienda=item.tienda,
                producto=item.variante.producto,
                tipo_evento=EventoUsuario.TipoEvento.CART,
            )
        except Exception:
            pass

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
    para el total actual del carrito del cliente (CU-19).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not getattr(settings, 'STRIPE_SECRET_KEY', None):
            return Response(
                {'error': 'La pasarela de pago Stripe no está configurada en el servidor.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        carritos = Carrito.objects.filter(
            cliente=request.user
        ).prefetch_related('items__variante')

        total_bs = _total_carrito_bs(carritos)
        if total_bs <= Decimal('0'):
            return Response(
                {'error': 'El carrito de compras está vacío.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        monto_usd_centavos = _usd_centavos(total_bs)
        tasa = Decimal(str(getattr(settings, 'STRIPE_USD_BOB_RATE', 6.96)))
        if tasa <= Decimal('0'):
            tasa = Decimal('6.96')
        monto_usd_decimal = (total_bs / tasa).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            intent = stripe.PaymentIntent.create(
                amount=monto_usd_centavos,
                currency='usd',
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
                'publishable_key': getattr(settings, 'STRIPE_PUBLISHABLE_KEY', ''),
                'monto_bs': str(total_bs),
                'monto_usd': str(monto_usd_decimal),
            },
            status=status.HTTP_200_OK,
        )


class CheckoutView(APIView):
    """POST /api/pedidos/carrito/checkout/ — Procesa la compra de los carritos del cliente,
    generando Pedido e ItemPedido por cada tienda, activando los triggers de PostgreSQL
    que descuentan el stock (trg_actualizar_stock_item_pedido con SELECT FOR UPDATE) y
    calculan totales (trg_recalcular_total_pedido). Registra además el Pago (CU-19):
    con `metodo_pago: "stripe"` exige un `payment_intent_id` confirmado cuyo monto
    coincida con el carrito; con cualquier otro valor (efectivo, QR) el pago queda
    `pendiente` (cobro contra entrega).
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
        es_stripe = metodo_pago_valor.lower() in ('stripe', 'tarjeta', 'tarjeta (stripe)')
        payment_intent_id = str(request.data.get('payment_intent_id') or '').strip()

        if es_stripe:
            if not payment_intent_id:
                return Response(
                    {'error': 'Falta el identificador del pago con tarjeta (payment_intent_id).'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not getattr(settings, 'STRIPE_SECRET_KEY', None):
                return Response(
                    {'error': 'La pasarela de pago Stripe no está configurada en el servidor.'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
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
                    {'error': f'El pago con tarjeta todavía no se completó (estado actual: {intent.status}).'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            total_bs_actual = _total_carrito_bs(carritos)
            monto_esperado = _usd_centavos(total_bs_actual)
            # Tolerancia de 1 centavo de USD por redondeo entre el intento y el recálculo
            if abs(intent.amount - monto_esperado) > 1:
                return Response(
                    {'error': 'El monto pagado no coincide con el total actual del carrito.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            metodo_pago_nombre = NOMBRE_METODO_STRIPE
        elif metodo_pago_valor.lower() == 'qr':
            metodo_pago_nombre = NOMBRE_METODO_QR
        elif metodo_pago_valor.lower() in ('efectivo', ''):
            metodo_pago_nombre = NOMBRE_METODO_EFECTIVO
        else:
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

                    # 1. Crear pedido inicial (subtotal y total serán fijados por trg_recalcular_total_pedido)
                    pedido = Pedido.objects.create(
                        cliente=request.user,
                        tienda=carrito.tienda,
                        estado_actual='completado',
                        subtotal=Decimal('0.00'),
                        total=Decimal('0.00'),
                    )

                    for item in items:
                        # 2. Al insertar en item_pedido se dispara trg_actualizar_stock_item_pedido
                        # que ejecuta SELECT ... FOR UPDATE, descuenta variante.stock y verifica disponibilidad.
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

                    # 3. Vaciar items de este carrito
                    carrito.items.all().delete()

                    # 4. REGLA INQUEBRANTABLE DE BD:
                    # El trigger fn_recalcular_total_pedido ya fijó pedido.subtotal y pedido.total en BD.
                    # Recargamos la instancia desde PostgreSQL para que el Pago guarde el monto real exacto.
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
    permission_classes = [permissions.IsAuthenticated, IsClienteUser]

    def get(self, request):
        pedidos = (
            Pedido.objects.filter(cliente=request.user)
            .select_related('tienda')
            .prefetch_related('items__variante__producto', 'historial_estados', 'envios__direccion_envio')
            .order_by('-fecha')[:20]
        )
        data = []
        for p in pedidos:
            items = []
            for it in p.items.all():
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
            envio = max(p.envios.all(), key=lambda e: e.id, default=None)
            data.append({
                'id': p.id,
                'tienda_id': p.tienda_id,
                'tienda_nombre': p.tienda.nombre if p.tienda else 'Tienda',
                'estado': estados.normalizar(p.estado_actual),
                'estado_etiqueta': estados.etiqueta(p.estado_actual),
                'subtotal': str(p.subtotal),
                'total': str(p.total),
                'fecha': p.fecha.isoformat() if p.fecha else None,
                'items': items,
                'historial': [
                    historial_a_dict(h)
                    for h in sorted(p.historial_estados.all(), key=lambda h: (h.fecha, h.id))
                ],
                'envio': envio_a_dict(envio),
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
