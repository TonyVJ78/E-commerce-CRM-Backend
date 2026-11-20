"""Carga de los datos de una tienda como arreglos numpy para los modelos de ML.

Los pedidos cancelados no cuentan como compra en ningún modelo. Las fechas se
llevan al día local (America/La_Paz) y se manejan como ordinales enteros.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import numpy as np
from django.db.models import Count
from django.utils import timezone

from apps.catalogo.models import Producto
from apps.marketing.models import CuponUso
from apps.pedidos import estados
from apps.pedidos.models import ItemPedido, Pedido, Resena
from apps.usuarios.models import Usuario

from ..models import EventoUsuario

DOMINIO_SINTETICO = '@sintetico.kantu.bo'


class DatosInsuficientes(Exception):
    """La tienda no tiene datos suficientes para entrenar un modelo."""


@dataclass
class DatosTienda:
    hasta: date
    pedido_id: np.ndarray
    pedido_cliente: np.ndarray
    pedido_dia: np.ndarray
    pedido_total: np.ndarray
    pedido_con_cupon: np.ndarray
    resena_cliente: np.ndarray
    resena_dia: np.ndarray
    resena_calificacion: np.ndarray
    productos_por_pedido: dict[int, frozenset[int]]
    nombres_producto: dict[int, str]
    tienda_id: int


def _dia_local(instante: datetime) -> int:
    return timezone.localtime(instante).date().toordinal()


def cargar(tienda, hasta: date | None = None) -> DatosTienda:
    hasta = hasta or timezone.localdate()
    pedidos = list(
        Pedido.objects.filter(tienda=tienda)
        .exclude(estado_actual=estados.CANCELADO)
        .order_by('id')
        .values_list('id', 'cliente_id', 'fecha', 'total')
    )
    con_cupon = set(CuponUso.objects.filter(tienda=tienda).values_list('pedido_id', flat=True))
    resenas = list(Resena.objects.filter(tienda=tienda).values_list('cliente_id', 'fecha', 'calificacion'))

    productos_por_pedido: dict[int, set[int]] = {}
    items = (ItemPedido.objects.filter(tienda=tienda)
             .exclude(pedido__estado_actual=estados.CANCELADO)
             .values_list('pedido_id', 'variante__producto_id'))
    for pedido_id, producto_id in items:
        productos_por_pedido.setdefault(pedido_id, set()).add(producto_id)

    nombres = dict(Producto.objects.filter(tienda=tienda).values_list('id', 'nombre'))

    return DatosTienda(
        hasta=hasta,
        pedido_id=np.array([p[0] for p in pedidos], dtype=np.int64),
        pedido_cliente=np.array([p[1] for p in pedidos], dtype=np.int64),
        pedido_dia=np.array([_dia_local(p[2]) for p in pedidos], dtype=np.int64),
        pedido_total=np.array([float(p[3]) for p in pedidos]),
        pedido_con_cupon=np.array([p[0] in con_cupon for p in pedidos], dtype=bool),
        resena_cliente=np.array([r[0] for r in resenas], dtype=np.int64),
        resena_dia=np.array([_dia_local(r[1]) for r in resenas], dtype=np.int64),
        resena_calificacion=np.array([r[2] for r in resenas], dtype=float),
        productos_por_pedido={k: frozenset(v) for k, v in productos_por_pedido.items()},
        nombres_producto=nombres,
        tienda_id=tienda.id,
    )


def eventos_por_cliente(tienda_id: int, desde: date, hasta_exclusivo: date) -> dict[int, int]:
    """Eventos de navegación por cliente en [desde, hasta_exclusivo)."""
    zona = timezone.get_current_timezone()
    inicio = timezone.make_aware(datetime.combine(desde, time.min), zona)
    fin = timezone.make_aware(datetime.combine(hasta_exclusivo, time.min), zona)
    filas = (EventoUsuario.objects
             .filter(tienda_id=tienda_id, cliente__isnull=False, fecha__gte=inicio, fecha__lt=fin)
             .values('cliente_id')
             .annotate(n=Count('id')))
    return {f['cliente_id']: f['n'] for f in filas}


def serie_diaria(datos: DatosTienda) -> tuple[np.ndarray, np.ndarray]:
    """Ingresos por día desde el primer pedido hasta `hasta`; los días sin ventas valen 0."""
    primero = int(datos.pedido_dia.min())
    ultimo = datos.hasta.toordinal()
    dias = np.arange(primero, ultimo + 1)
    en_rango = datos.pedido_dia <= ultimo
    ingresos = np.bincount(
        datos.pedido_dia[en_rango] - primero,
        weights=datos.pedido_total[en_rango],
        minlength=len(dias),
    )
    return dias, ingresos


def nombres_clientes(ids: list[int]) -> dict[int, tuple[str, str]]:
    usuarios = Usuario.objects.filter(id__in=ids).values_list('id', 'first_name', 'last_name', 'email')
    return {i: (f'{n} {a}'.strip() or correo.split('@')[0], correo) for i, n, a, correo in usuarios}


def resumen_dataset(tienda) -> dict:
    """Ficha del dataset de la tienda: lo que hay en la base, no solo lo que entra al entrenamiento."""
    pedidos = Pedido.objects.filter(tienda=tienda)
    clientes = pedidos.values('cliente_id').distinct().count()
    sinteticos = (pedidos.filter(cliente__email__endswith=DOMINIO_SINTETICO)
                  .values('cliente_id').distinct().count())
    extremos = pedidos.order_by('fecha').values_list('fecha', flat=True)
    primero = extremos.first()
    ultimo = extremos.last()
    return {
        'pedidos': pedidos.count(),
        'pedidos_cancelados': pedidos.filter(estado_actual=estados.CANCELADO).count(),
        'clientes': clientes,
        'eventos': EventoUsuario.objects.filter(tienda=tienda).count(),
        'resenas': Resena.objects.filter(tienda=tienda).count(),
        'desde': timezone.localtime(primero).date().isoformat() if primero else None,
        'hasta': timezone.localtime(ultimo).date().isoformat() if ultimo else None,
        'sintetico': clientes > 0 and sinteticos * 2 > clientes,
    }
