"""
CU-22 — Gestionar pedidos recibidos.

La empresa lista los pedidos de una de sus tiendas y avanza su estado; es el
mismo `estado_actual` que el cliente ve en "Mis pedidos" (CU-20). Toda consulta
parte de `get_tienda()`, que exige que la tienda sea del usuario autenticado.
"""

from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalogo.models import Variante
from apps.tiendas.models import Tienda
from apps.usuarios.audit import ACCION_ACTUALIZAR, registrar_auditoria
from apps.usuarios.permissions import IsEmpresa, PermisoModulo

from . import estados
from .models import DireccionEnvio, Envio, Pedido
from .presentacion import envio_a_dict, historial_a_dict, item_a_dict, pago_a_dict

LIMITE_LISTADO = 200


class PedidosTiendaMixin:
    permission_classes = [permissions.IsAuthenticated, IsEmpresa, PermisoModulo('pedidos')]

    def get_tienda(self):
        return get_object_or_404(
            Tienda,
            pk=self.kwargs['tienda_id'],
            propietario=self.request.user,
        )

    def get_pedido(self, tienda):
        return get_object_or_404(
            Pedido.objects.select_related('cliente'),
            pk=self.kwargs['pedido_id'],
            tienda=tienda,
        )


def _cliente_a_dict(cliente):
    nombre = f'{cliente.first_name} {cliente.last_name}'.strip()
    return {'id': cliente.id, 'email': cliente.email, 'nombre': nombre or cliente.email}


def _pedido_resumen(pedido):
    return {
        'id': pedido.id,
        'cliente': _cliente_a_dict(pedido.cliente),
        'estado': estados.normalizar(pedido.estado_actual),
        'estado_etiqueta': estados.etiqueta(pedido.estado_actual),
        'siguientes_estados': estados.siguientes(pedido.estado_actual),
        'fecha': pedido.fecha.isoformat() if pedido.fecha else None,
        'total': str(pedido.total),
        'cantidad_items': getattr(pedido, 'cantidad_items', None) or 0,
    }


def _pedido_detalle(pedido):
    items = list(pedido.items.select_related('variante__producto'))
    pago = pedido.pagos.select_related('metodo_pago').first()
    envio = pedido.envios.select_related('direccion_envio').order_by('-id').first()
    return {
        **_pedido_resumen(pedido),
        'subtotal': str(pedido.subtotal),
        'cantidad_items': sum(it.cantidad for it in items),
        'items': [item_a_dict(it) for it in items],
        'pago': pago_a_dict(pago),
        'envio': envio_a_dict(envio),
        'historial': [historial_a_dict(h) for h in pedido.historial_estados.order_by('fecha', 'id')],
    }


class PedidosTiendaListView(PedidosTiendaMixin, APIView):
    """GET /api/tiendas/<tienda_id>/pedidos/?estado=<estado>&q=<texto>

    Devuelve los pedidos más recientes y el conteo por estado para las pestañas.
    `q` busca por número de pedido o por nombre/email del cliente.
    """

    def get(self, request, tienda_id):
        tienda = self.get_tienda()
        base = Pedido.objects.filter(tienda=tienda)

        conteos = dict.fromkeys(estados.ESTADOS, 0)
        for fila in base.values('estado_actual').annotate(n=Count('id')):
            clave = estados.normalizar(fila['estado_actual'])
            conteos[clave] = conteos.get(clave, 0) + fila['n']

        qs = base.select_related('cliente').annotate(cantidad_items=Sum('items__cantidad'))

        estado = (request.query_params.get('estado') or '').strip().lower()
        if estado == estados.PENDIENTE:
            qs = qs.filter(estado_actual__in=[estados.PENDIENTE, estados.COMPLETADO_LEGADO])
        elif estado:
            qs = qs.filter(estado_actual=estado)

        texto = (request.query_params.get('q') or '').strip().lstrip('#')
        if texto:
            filtro = (
                Q(cliente__email__icontains=texto)
                | Q(cliente__first_name__icontains=texto)
                | Q(cliente__last_name__icontains=texto)
            )
            if texto.isdigit():
                filtro |= Q(pk=int(texto))
            qs = qs.filter(filtro)

        pedidos = qs.order_by('-fecha', '-id')[:LIMITE_LISTADO]
        return Response({
            'tienda': {'id': tienda.id, 'nombre': tienda.nombre},
            'conteos': conteos,
            'total': sum(conteos.values()),
            'pedidos': [_pedido_resumen(p) for p in pedidos],
        })


class PedidoTiendaDetailView(PedidosTiendaMixin, APIView):
    """GET /api/tiendas/<tienda_id>/pedidos/<pedido_id>/"""

    def get(self, request, tienda_id, pedido_id):
        return Response(_pedido_detalle(self.get_pedido(self.get_tienda())))


class PedidoTiendaEstadoView(PedidosTiendaMixin, APIView):
    """PATCH /api/tiendas/<tienda_id>/pedidos/<pedido_id>/estado/

    Body: `{"estado", "transportista"?, "numero_seguimiento"?}`; los dos últimos
    solo se usan al pasar a `enviado`. El historial lo escribe el trigger
    `trg_registrar_historial_estado_pedido`.
    """

    def patch(self, request, tienda_id, pedido_id):
        tienda = self.get_tienda()
        nuevo = str(request.data.get('estado') or '').strip().lower()
        if nuevo not in estados.ESTADOS:
            return Response(
                {'error': 'Estado no válido.', 'estados_validos': estados.ESTADOS},
                status=status.HTTP_400_BAD_REQUEST,
            )

        transportista = str(request.data.get('transportista') or '').strip()[:50]
        numero_seguimiento = str(request.data.get('numero_seguimiento') or '').strip()[:50]

        with transaction.atomic():
            pedido = get_object_or_404(
                Pedido.objects.select_for_update(),
                pk=pedido_id,
                tienda=tienda,
            )
            anterior = pedido.estado_actual
            if not estados.puede_transicionar(anterior, nuevo):
                return Response(
                    {
                        'error': (
                            f'No se puede pasar un pedido de "{estados.etiqueta(anterior)}" '
                            f'a "{estados.etiqueta(nuevo)}".'
                        ),
                        'siguientes_estados': estados.siguientes(anterior),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            pedido.estado_actual = nuevo
            pedido.save(update_fields=['estado_actual'])
            aviso = self._aplicar_efectos(pedido, nuevo, transportista, numero_seguimiento)

        registrar_auditoria(
            request,
            ACCION_ACTUALIZAR,
            tabla='pedido',
            registro_id=pedido.id,
            datos_anteriores={'estado_actual': anterior},
            datos_nuevos={'estado_actual': nuevo},
        )

        data = _pedido_detalle(self.get_pedido(tienda))
        data['mensaje'] = f'Pedido #{pedido.id} actualizado a "{estados.etiqueta(nuevo)}".'
        if aviso:
            data['aviso'] = aviso
        return Response(data)

    def _aplicar_efectos(self, pedido, nuevo, transportista, numero_seguimiento):
        """Efectos secundarios del cambio de estado. Devuelve un aviso o None."""
        ahora = timezone.now()

        if nuevo == estados.ENVIADO:
            envio = pedido.envios.order_by('-id').first()
            if envio is None:
                # `Envio` exige dirección y aún no hay CU para registrarlas.
                direccion = (
                    DireccionEnvio.objects
                    .filter(cliente=pedido.cliente, tienda=pedido.tienda)
                    .order_by('-es_predeterminada', '-id')
                    .first()
                )
                if direccion is None:
                    return (
                        'El cliente no tiene una dirección de envío registrada en esta '
                        'tienda; no se generó el registro de envío.'
                    )
                envio = Envio(tienda=pedido.tienda, pedido=pedido, direccion_envio=direccion)
            envio.transportista = transportista or envio.transportista
            envio.numero_seguimiento = numero_seguimiento or envio.numero_seguimiento
            envio.fecha_envio = ahora
            envio.save()

        elif nuevo == estados.ENTREGADO:
            pedido.envios.filter(fecha_entrega__isnull=True).update(fecha_entrega=ahora)
            # Pago contra entrega: se cobra al entregar.
            pedido.pagos.filter(estado='pendiente').update(estado='pagado')

        elif nuevo == estados.CANCELADO:
            for item in pedido.items.all():
                Variante.objects.filter(pk=item.variante_id).update(stock=F('stock') + item.cantidad)
            pedido.pagos.filter(estado='pendiente').update(estado='anulado')
            if pedido.pagos.filter(estado='pagado').exists():
                return (
                    'El pedido ya estaba pagado con tarjeta: el reembolso se debe '
                    'gestionar manualmente en Stripe.'
                )
        return None
