"""Cotización del lado del servidor y aplicación atómica de cupones (CU-27)."""
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from apps.crm.models import FichaCliente, Segmento, SegmentoCliente
from .models import Cupon, CuponUso


def es_destinatario(cupon, cliente):
    segmento_id = cupon.segmento_objetivo_id
    if not segmento_id and cupon.campana_id:
        if cupon.campana.tienda_id != cupon.tienda_id:
            return False
        segmento_id = cupon.campana.segmento_objetivo_id
    if segmento_id:
        segmento = Segmento.objects.filter(pk=segmento_id, tienda_id=cupon.tienda_id).first()
        if segmento is None:
            return False
        if segmento.criterio.startswith('rfm:'):
            return SegmentoCliente.objects.filter(cliente=cliente, tienda_id=cupon.tienda_id,
                segmento=segmento.criterio.removeprefix('rfm:')).exists()
    return not segmento_id or FichaCliente.objects.filter(
        cliente=cliente, tienda_id=cupon.tienda_id, segmento_id=segmento_id,
    ).exists()


def normalizar_codigos(codigos):
    if codigos is None:
        return {}
    if not isinstance(codigos, dict):
        raise ValidationError({'cupones': 'Indica un código por tienda.'})
    salida = {}
    for tienda, codigo in codigos.items():
        try:
            tienda_id = int(tienda)
        except (ValueError, TypeError):
            raise ValidationError({'cupones': 'La tienda del cupón no es válida.'})
        if tienda_id <= 0 or not isinstance(codigo, str) or len(codigo.strip()) > 30:
            raise ValidationError({'cupones': 'El código de cupón no es válido.'})
        if codigo.strip():
            salida[str(tienda_id)] = codigo.strip().upper()
    return salida


def cotizar_carritos(carritos, cliente, codigos=None, *, bloquear=False):
    codigos = normalizar_codigos(codigos)
    activos = []
    for carrito in carritos:
        items = list(carrito.items.all())
        if items:
            activos.append((carrito, sum((it.cantidad * it.variante.precio for it in items), Decimal('0.00'))))
    tiendas = [str(carrito.tienda_id) for carrito, _ in activos]
    if set(codigos) - set(tiendas):
        raise ValidationError({'cupones': 'El cupón debe pertenecer a una tienda de tu carrito.'})
    if codigos and len(tiendas) != len(set(tiendas)):
        raise ValidationError({'cupones': 'Existen varios carritos de la misma tienda. Contacta a soporte antes de aplicar un cupón.'})
    resultado = {}
    for carrito, subtotal in sorted(activos, key=lambda entry: entry[0].tienda_id):
        descuento = Decimal('0.00')
        cupon = None
        codigo = codigos.get(str(carrito.tienda_id))
        if codigo:
            qs = Cupon.objects.select_related('campana')
            if bloquear:
                qs = qs.select_for_update(of=('self',))
            cupon = qs.filter(tienda_id=carrito.tienda_id, codigo__iexact=codigo).first()
            hoy = timezone.localdate()
            if not cupon or not cupon.activo or not (cupon.fecha_inicio <= hoy <= cupon.fecha_expiracion):
                raise ValidationError({'cupones': 'El cupón no está activo o está fuera de vigencia.'})
            if not es_destinatario(cupon, cliente):
                raise ValidationError({'cupones': 'El cupón no corresponde a tu segmento de cliente.'})
            if cupon.usos.count() >= cupon.usos_maximos:
                raise ValidationError({'cupones': 'El cupón agotó sus usos disponibles.'})
            if cupon.usos.filter(pedido__cliente=cliente).count() >= cupon.limite_por_cliente:
                raise ValidationError({'cupones': 'Alcanzaste el límite de uso de este cupón.'})
            if subtotal < cupon.monto_minimo:
                raise ValidationError({'cupones': f'El cupón requiere una compra mínima de Bs {cupon.monto_minimo}.'})
            if cupon.valor_descuento <= 0:
                raise ValidationError({'cupones': 'El valor del cupón no es válido.'})
            if cupon.tipo_descuento == 'porcentaje' and cupon.valor_descuento <= 100:
                descuento = subtotal * cupon.valor_descuento / Decimal(100)
            elif cupon.tipo_descuento in ('monto_fijo', 'fijo', 'monto'):
                descuento = cupon.valor_descuento
            else:
                raise ValidationError({'cupones': 'El tipo de descuento no es válido.'})
            descuento = min(subtotal, descuento.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
        resultado[carrito.id] = {'cupon': cupon, 'subtotal': subtotal, 'descuento': descuento,
                                 'total': subtotal - descuento, 'tienda_id': carrito.tienda_id}
    return resultado


def registrar_descuento(pedido, cotizacion):
    cupon = cotizacion['cupon']
    if cupon:
        # Los triggers recalculan los items. Aplicar después el descuento preserva
        # el subtotal real y hace que Pago.monto use el total descontado.
        pedido.total = pedido.subtotal - cotizacion['descuento']
        pedido.save(update_fields=['total'])
        CuponUso.objects.create(tienda=pedido.tienda, cupon=cupon, pedido=pedido)


def json_cotizacion(cotizacion):
    cupon = cotizacion['cupon']
    return {key: str(cotizacion[key]) for key in ('subtotal', 'descuento', 'total')} | {
        'tienda_id': cotizacion['tienda_id'], 'codigo': cupon.codigo if cupon else None,
    }
