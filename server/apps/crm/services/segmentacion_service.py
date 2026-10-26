"""Cálculo transaccional de segmentos RFM por tienda."""

from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count, Max, Q, Subquery, Sum
from django.utils import timezone

from apps.crm.models import ReglaSegmentacion, SegmentoCliente, Segmento
from apps.pedidos import estados
from apps.pedidos.models import Pedido
from apps.tiendas.models import Tienda


SEGMENTOS = [choice[0] for choice in SegmentoCliente.SEGMENTO_CHOICES]


def _clasificar(metrica, reglas, ahora):
    dias_desde_ultima = (ahora - metrica['ultima_compra']).days
    if dias_desde_ultima >= reglas.dias_inactividad:
        return SegmentoCliente.INACTIVO
    if (
        metrica['monto_total_gastado'] > reglas.umbral_alto_valor
        or metrica['ticket_promedio'] > reglas.umbral_alto_valor
    ):
        return SegmentoCliente.ALTO_VALOR
    if metrica['total_compras'] >= reglas.min_compras_frecuente:
        return SegmentoCliente.FRECUENTE
    return SegmentoCliente.NUEVO


@transaction.atomic
def recalcular_segmentos_tienda(tienda: Tienda):
    """Recalcula métricas y segmentos de todos los clientes compradores de la tienda."""
    # Share automatic groups with the CU-27 selector without overwriting manual CRM segments.
    Tienda.objects.select_for_update().get(pk=tienda.pk)
    for codigo, etiqueta in SegmentoCliente.SEGMENTO_CHOICES:
        Segmento.objects.get_or_create(tienda=tienda, criterio=f'rfm:{codigo}',
            defaults={'nombre': f'Automático: {etiqueta}'})
    reglas, _ = ReglaSegmentacion.objects.get_or_create(tienda=tienda)
    ahora = timezone.now()
    ids_pedidos_confirmados = (
        Pedido.objects.filter(tienda=tienda)
        .exclude(estado_actual=estados.CANCELADO)
        .filter(
            Q(estado_actual__in=[estados.PROCESADO, estados.ENTREGADO])
            | Q(pagos__estado='pagado')
        )
        .values('pk')
    )
    pedidos_confirmados = Pedido.objects.filter(
        tienda=tienda,
        cliente__rol__nombre='cliente',
        pk__in=Subquery(ids_pedidos_confirmados),
    )
    metricas = list(
        pedidos_confirmados.values('cliente_id')
        .annotate(
            total_compras=Count('id'),
            monto_total_gastado=Sum('total'),
            ticket_promedio=Avg('total'),
            ultima_compra=Max('fecha'),
        )
        .order_by()
    )
    clientes_actualizados = set()

    for metrica in metricas:
        total = metrica['monto_total_gastado'] or Decimal('0.00')
        ticket = metrica['ticket_promedio'] or Decimal('0.00')
        datos = {
            'segmento': _clasificar(
                {
                    **metrica,
                    'monto_total_gastado': total,
                    'ticket_promedio': ticket,
                },
                reglas,
                ahora,
            ),
            'total_compras': metrica['total_compras'],
            'monto_total_gastado': total,
            'ticket_promedio': ticket,
            'ultima_compra': metrica['ultima_compra'],
        }
        SegmentoCliente.objects.update_or_create(
            tienda=tienda,
            cliente_id=metrica['cliente_id'],
            defaults=datos,
        )
        clientes_actualizados.add(metrica['cliente_id'])

    SegmentoCliente.objects.filter(tienda=tienda).exclude(
        cliente_id__in=clientes_actualizados
    ).delete()
    return resumen_segmentacion_tienda(tienda)


def resumen_segmentacion_tienda(tienda: Tienda):
    """Devuelve conteos, distribución porcentual y ticket medio por segmento."""
    agregados = {
        fila['segmento']: fila
        for fila in (
            SegmentoCliente.objects.filter(tienda=tienda)
            .values('segmento')
            .annotate(total=Count('id'), ticket_promedio=Avg('ticket_promedio'))
        )
    }
    total_clientes = sum(fila['total'] for fila in agregados.values())
    segmentos = {}
    for segmento in SEGMENTOS:
        fila = agregados.get(segmento, {})
        cantidad = fila.get('total', 0)
        segmentos[segmento] = {
            'total': cantidad,
            'porcentaje': round(cantidad * 100 / total_clientes, 2) if total_clientes else 0,
            'ticket_promedio': fila.get('ticket_promedio') or Decimal('0.00'),
        }
    return {'total_clientes': total_clientes, 'segmentos': segmentos}
