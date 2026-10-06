"""Representación JSON de un pedido, compartida por "Mis pedidos" (CU-20) y CU-22."""

from . import estados


def imagen_producto(producto):
    imgs = getattr(producto, 'imagenes', None)
    if imgs:
        first = imgs[0]
        if isinstance(first, dict):
            return first.get('url', '')
        return str(first)
    return ''


def item_a_dict(item):
    variante = item.variante
    producto = variante.producto if variante else None
    return {
        'id': item.id,
        'producto_id': producto.id if producto else None,
        'producto_nombre': producto.nombre if producto else 'Producto',
        'producto_imagen': imagen_producto(producto) if producto else '',
        'variante_id': variante.id if variante else None,
        'variante_nombre': variante.nombre if variante else 'Unica',
        'variante_sku': variante.sku if variante else '',
        'cantidad': item.cantidad,
        'precio_unitario': str(item.precio_unitario),
        'subtotal': f'{item.cantidad * item.precio_unitario:.2f}',
    }


def historial_a_dict(historial):
    return {
        'estado': estados.normalizar(historial.estado),
        'estado_etiqueta': estados.etiqueta(historial.estado),
        'fecha': historial.fecha.isoformat() if historial.fecha else None,
    }


def pago_a_dict(pago):
    if pago is None:
        return None
    return {
        'metodo': pago.metodo_pago.nombre if pago.metodo_pago else 'Efectivo',
        'estado': pago.estado,
        'monto': str(pago.monto),
        'referencia': pago.referencia_transaccion,
        'fecha': pago.fecha.isoformat() if pago.fecha else None,
    }


def envio_a_dict(envio):
    if envio is None:
        return None
    direccion = envio.direccion_envio
    return {
        'transportista': envio.transportista,
        'numero_seguimiento': envio.numero_seguimiento,
        'fecha_envio': envio.fecha_envio.isoformat() if envio.fecha_envio else None,
        'fecha_entrega': envio.fecha_entrega.isoformat() if envio.fecha_entrega else None,
        'direccion': f'{direccion.direccion}, {direccion.ciudad}' if direccion else '',
    }
