"""Servicios de identidad de marca, contexto autorizado y panel de tienda."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.catalogo.models import Producto, Variante
from apps.catalogo.services import CloudinaryUploadError, _cloudinary_uploader
from apps.pedidos.models import ItemPedido, Pedido

from .models import Tienda


def resolver_tienda_autorizada(usuario, tienda_id=None):
    """Misma política que el catálogo: empresa propietaria; ajena e inexistente = 404."""
    tiendas = Tienda.objects.filter(propietario=usuario)
    if tienda_id is None:
        disponibles = list(tiendas[:2])
        if len(disponibles) != 1:
            raise ValidationError({'tienda_id': 'Selecciona una tienda para consultar el panel.'})
        return disponibles[0]
    try:
        tienda_id = int(tienda_id)
    except (ValueError, TypeError):
        raise ValidationError({'tienda_id': 'Ingresa un identificador de tienda válido.'})
    if tienda_id <= 0:
        raise ValidationError({'tienda_id': 'Ingresa un identificador de tienda válido.'})
    return get_object_or_404(tiendas, pk=tienda_id)


def consultar_alertas_stock(tienda):
    """Inventario vigente: una fila por variante activa, estrictamente bajo el mínimo."""
    variantes = Variante.objects.filter(
        producto__tienda=tienda, activa=True, stock__lt=F('stock_minimo'),
    ).select_related('producto').order_by('stock', 'producto__nombre', 'id')
    return [
        {
            'producto_id': variante.producto_id,
            'producto_nombre': variante.producto.nombre,
            'variante_id': variante.id,
            'variante_nombre': variante.nombre,
            'sku': variante.sku,
            'stock': variante.stock,
            'stock_minimo': variante.stock_minimo,
        }
        for variante in variantes
    ]


def consultar_panel_tienda(tienda):
    productos = Producto.objects.filter(tienda=tienda).aggregate(
        total_productos=Count('id'),
        productos_activos=Count('id', filter=Q(activo=True)),
    )
    pedidos = Pedido.objects.filter(tienda=tienda).aggregate(
        total_pedidos=Count('id'),
        pedidos_pendientes=Count('id', filter=Q(estado_actual='pendiente')),
        ingresos_totales=Sum('total', filter=~Q(estado_actual__iexact='cancelado')),
    )
    pedidos['ingresos_totales'] = pedidos['ingresos_totales'] or Decimal('0.00')
    alertas = consultar_alertas_stock(tienda)
    hoy = timezone.localdate()
    inicio = hoy - timedelta(days=6)
    ventas = (
        ItemPedido.objects.filter(
            tienda=tienda, pedido__tienda=tienda, variante__producto__tienda=tienda,
            pedido__fecha__date__gte=inicio, pedido__fecha__date__lte=hoy,
        )
        .exclude(pedido__estado_actual__iexact='cancelado')
        .order_by()
        .annotate(dia=TruncDate('pedido__fecha'))
        .values('dia').annotate(unidades=Sum('cantidad'))
    )
    por_dia = {venta['dia']: venta['unidades'] for venta in ventas}
    return {
        'tienda': tienda,
        'tienda_id': tienda.id,
        'tienda_nombre': tienda.nombre,
        **productos, **pedidos,
        'productos_bajo_stock': len(alertas),
        'alertas_stock': alertas,
        'ventas_semana': [
            {'fecha': (inicio + timedelta(days=i)).isoformat(),
             'cantidad': por_dia.get(inicio + timedelta(days=i), 0)}
            for i in range(7)
        ],
    }


def upload_store_logo(image, tienda_id):
    """Sube un logo ya validado a una carpeta aislada por tienda."""
    uploader = _cloudinary_uploader()
    folder = f'kantu/tiendas/{tienda_id}/logo'

    try:
        result = uploader.upload(
            image,
            folder=folder,
            resource_type='image',
            use_filename=False,
            unique_filename=True,
            overwrite=False,
        )
    except Exception as exc:
        raise CloudinaryUploadError(
            'No se pudo subir el logotipo. Intenta nuevamente.'
        ) from exc

    url = result.get('secure_url', '')
    if not url:
        raise CloudinaryUploadError(
            'El proveedor de imágenes no devolvió una URL para el logotipo.'
        )

    return {
        'url': url,
        'public_id': result.get('public_id', ''),
    }


def delete_uploaded_logo(public_id):
    """Compensa una subida cuando el guardado posterior de la tienda falla."""
    if not public_id:
        return
    try:
        _cloudinary_uploader().destroy(
            public_id,
            resource_type='image',
            invalidate=True,
        )
    except Exception:
        # No se oculta el error original de base de datos/validación.
        return
