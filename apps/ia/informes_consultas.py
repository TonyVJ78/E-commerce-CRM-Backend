"""
Motor de consultas de los informes con IA (CU-34).

El modelo de lenguaje **no escribe SQL**. Describe la consulta con una
especificación cerrada —fuente, columnas para agrupar, métricas, filtros,
orden y límite— y este módulo la traduce a una consulta del ORM. Así:

- Solo se puede leer lo que está en `FUENTES`: nada de usuarios, contraseñas,
  tokens ni tablas internas.
- Cada consulta se limita **siempre** a las tiendas que el usuario puede ver
  (`tiendas_permitidas`); el filtro de tienda que pida el modelo solo puede
  achicar ese conjunto, nunca ampliarlo.
- Una especificación inválida devuelve un error legible para que el modelo la
  corrija, en vez de romper la petición.
- Los KPI que cruzan tablas (ganancia menos gastos, embudo de conversión,
  rotación de inventario...) son **fuentes combinadas definidas aquí**: cada una
  junta componentes del ORM por sus columnas de agrupación. El modelo nunca
  pide uniones.
"""

from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import (
    Avg, BooleanField, Count, DecimalField, DurationField, ExpressionWrapper, F, Max, Min,
    OuterRef, Q, Subquery, Sum,
)
from django.db.models.functions import Coalesce, TruncDay, TruncMonth, TruncWeek
from django.utils import timezone

from apps.catalogo.models import Variante
from apps.crm.models import RegistroRecuperacionCarrito
from apps.finanzas.models import GastoOperativo
from apps.marketing.models import CuponUso
from apps.pedidos import estados
from apps.pedidos.models import HistorialEstadoPedido, ItemPedido, Pago, Pedido, Resena
from apps.tiendas.models import Tienda

from .models import EventoUsuario


MAX_AGRUPAR = 3
MAX_METRICAS = 6
MAX_FILAS = 500
LIMITE_POR_DEFECTO = 50
# Filas que ve el modelo para analizar: el resto queda en la tabla. Ahorra
# tokens sin cambiar lo que el usuario recibe.
MAX_FILAS_PARA_MODELO = 40

# Tipos de columna: el frontend y los exportadores formatean según esto.
# Cada métrica dice además si es `sumable`: los conteos distintos (un pedido
# con dos productos cuenta en las dos filas), los promedios y los porcentajes
# no se totalizan. `VARIACION` es el cambio relativo entre periodos (en %) y
# `PUNTOS` la diferencia entre dos porcentajes (en puntos porcentuales).
TEXTO, ENTERO, MONEDA, DECIMAL, FECHA = 'texto', 'entero', 'moneda', 'decimal', 'fecha'
PORCENTAJE, VARIACION, PUNTOS = 'porcentaje', 'variacion', 'puntos'
NUMERICOS = (ENTERO, MONEDA, DECIMAL, PORCENTAJE, VARIACION, PUNTOS)

COMPARACIONES = {
    'periodo_anterior': 'periodo anterior',
    'mismo_periodo_anio_anterior': 'mismo periodo del año anterior',
}
MAX_METRICAS_COMPARANDO = 3


class ConsultaInvalida(ValueError):
    """La especificación no se puede ejecutar; el mensaje va al modelo."""


# ---------------------------------------------------------------------------
# Alcance por tenant
# ---------------------------------------------------------------------------

def es_administrador(usuario):
    return bool(usuario.is_superuser or (usuario.rol and usuario.rol.nombre == 'administrador'))


def tiendas_permitidas(usuario):
    """Tiendas cuyos datos puede consultar el usuario.

    El administrador ve todas. Cualquier otro rol, las que es propietario o a
    las que fue asignado como encargado (`UsuarioTienda`).
    """
    if es_administrador(usuario):
        return Tienda.objects.all()
    return Tienda.objects.filter(
        Q(propietario=usuario) | Q(usuarios_tienda__usuario=usuario)
    ).distinct()


# ---------------------------------------------------------------------------
# Catálogo de fuentes
# ---------------------------------------------------------------------------
# Cada dimensión: (etiqueta, tipo, campos para agrupar, campo a mostrar).
# Agrupar por id + nombre evita mezclar dos productos homónimos de tiendas
# distintas; en la tabla solo se muestra el nombre.
# Las dimensiones de tiempo usan `trunc` sobre el campo de fecha de la fuente.
#
# Una fuente simple es su propio y único componente (modelo, tienda, fecha,
# estado, dimensiones). Una fuente combinada declara varios `componentes`; cada
# métrica dice de cuál sale (`componente`) y las derivadas (cocientes,
# diferencias) se calculan después sobre las ya agregadas, junto a las filas
# de otros componentes con la misma clave de grupo.

def _dim(etiqueta, campos, mostrar=None, tipo=TEXTO, formato=None):
    campos = campos if isinstance(campos, (list, tuple)) else [campos]
    return {'etiqueta': etiqueta, 'campos': list(campos), 'mostrar': mostrar or campos[-1], 'tipo': tipo,
            'formato': formato}


def _tiempo(etiqueta, trunc):
    return {'etiqueta': etiqueta, 'trunc': trunc, 'tipo': FECHA}


def _met(titulo, tipo, expresion, sumable=False, componente=0, **extra):
    """Métrica agregada por la base de datos."""
    return {'titulo': titulo, 'tipo': tipo, 'expr': expresion, 'sumable': sumable, 'componente': componente, **extra}


def _derivada(titulo, tipo, depende, formula, sumable=False, **extra):
    """Métrica calculada con otras ya agregadas; `formula(valores, contexto)`."""
    return {'titulo': titulo, 'tipo': tipo, 'expr': None, 'sumable': sumable, 'depende': depende,
            'formula': formula, **extra}


def _cociente(titulo, tipo, numerador, denominador, factor=100, **extra):
    def formula(valores, contexto):
        if not valores[denominador]:
            return None
        return (valores[numerador] or 0) * factor / valores[denominador]
    return _derivada(titulo, tipo, [numerador, denominador], formula, **extra)


def _participacion(titulo, base):
    """Porcentaje que cada grupo aporta al total de `base` entre todos los grupos."""
    return _derivada(titulo, PORCENTAJE, [base], None, participacion=base)


_INGRESOS_ITEM = ExpressionWrapper(
    F('cantidad') * F('precio_unitario'), output_field=DecimalField(max_digits=14, decimal_places=2))
_COSTO_ITEM = ExpressionWrapper(
    F('cantidad') * F('costo_unitario'), output_field=DecimalField(max_digits=14, decimal_places=2))
_VALOR_STOCK = ExpressionWrapper(
    F('stock') * F('precio'), output_field=DecimalField(max_digits=16, decimal_places=2))

ESTADOS_PEDIDO = estados.ESTADOS

_TIENDA = _dim('Tienda', ['tienda_id', 'tienda__nombre'])
_TIEMPO = {'dia': _tiempo('Día', TruncDay), 'semana': _tiempo('Semana', TruncWeek), 'mes': _tiempo('Mes', TruncMonth)}

_DIMENSIONES_ITEM = {
    'tienda': _TIENDA,
    'producto': _dim('Producto', ['variante__producto_id', 'variante__producto__nombre']),
    'variante': _dim('Variante', ['variante_id', 'variante__producto__nombre', 'variante__nombre'],
                     mostrar='__variante__'),
    'categoria': _dim('Categoría', ['variante__producto__categoria__nombre']),
}
_DIMENSIONES_VARIANTE = {
    'tienda': _dim('Tienda', ['producto__tienda_id', 'producto__tienda__nombre']),
    'producto': _dim('Producto', ['producto_id', 'producto__nombre']),
    'variante': _dim('Variante', ['id', 'producto__nombre', 'nombre'], mostrar='__variante__'),
    'categoria': _dim('Categoría', ['producto__categoria__nombre']),
}

# Ganancia con el costo copiado al vender (`ItemPedido.costo_unitario`). Los
# ítems sin costo (pedidos viejos o variantes sin costo cargado) no se tratan
# como costo 0: quedan fuera de la ganancia y del margen, y se informa qué
# parte de las ventas es.
_METRICAS_GANANCIA = {
    'ingresos_con_costo': _met('Ingresos de ítems con costo (Bs)', MONEDA,
                               lambda: Sum(_INGRESOS_ITEM, filter=Q(costo_unitario__isnull=False)), True),
    'ingresos_sin_costo': _met('Ingresos de ítems sin costo (Bs)', MONEDA,
                               lambda: Sum(_INGRESOS_ITEM, filter=Q(costo_unitario__isnull=True)), True),
    'costo_mercaderia': _met('Costo de la mercadería vendida (Bs)', MONEDA, lambda: Sum(_COSTO_ITEM), True,
                             mejor_si='baja', avisa_costo=True),
    'ganancia_bruta': _derivada(
        'Ganancia bruta (Bs)', MONEDA, ['ingresos_con_costo', 'costo_mercaderia'],
        lambda v, c: (v['ingresos_con_costo'] or 0) - (v['costo_mercaderia'] or 0), sumable=True, avisa_costo=True),
    'margen_bruto_pct': _cociente('Margen bruto (%)', PORCENTAJE, 'ganancia_bruta', 'ingresos_con_costo',
                                  avisa_costo=True),
    'ventas_sin_costo_pct': _cociente('Ventas sin costo cargado (%)', PORCENTAJE, 'ingresos_sin_costo', 'ingresos',
                                      mejor_si='baja'),
}

_SIN_GASTOS_POR_PRODUCTO = 'Los gastos operativos son de toda la tienda y no se pueden asignar a un producto: se restaron completos.'

def _base_clientes(qs, filtros, tienda_ids):
    """Marca cada pedido con si su cliente compró por primera vez dentro del periodo."""
    inicio = _inicio_del_dia(_fecha(filtros['fecha_desde'], 'fecha_desde'))
    primera_compra = (
        Pedido.objects.filter(cliente=OuterRef('cliente'), tienda_id__in=tienda_ids)
        .exclude(estado_actual=estados.CANCELADO)
        .order_by().values('cliente').annotate(primera=Min('fecha')).values('primera')
    )
    return qs.annotate(_primera=Subquery(primera_compra)).annotate(
        _es_nuevo=ExpressionWrapper(Q(_primera__gte=inicio), output_field=BooleanField()))


def _base_entregas(qs, filtros, tienda_ids):
    """Pedidos entregados con su duración: desde el estado pendiente hasta el entregado."""
    historial = HistorialEstadoPedido.objects.filter(pedido=OuterRef('pk')).order_by('fecha')
    entrega = historial.filter(estado=estados.ENTREGADO).values('fecha')[:1]
    inicio = historial.filter(estado__in=[estados.PENDIENTE, estados.COMPLETADO_LEGADO]).values('fecha')[:1]
    return (
        qs.filter(estado_actual=estados.ENTREGADO)
        .annotate(_entrega=Subquery(entrega))
        .filter(_entrega__isnull=False)
        .annotate(_duracion=ExpressionWrapper(
            F('_entrega') - Coalesce(Subquery(inicio), F('fecha')), output_field=DurationField()))
    )


FUENTES = {
    'ventas_productos': {
        'descripcion': (
            'Líneas vendidas (ítems de pedidos). Para qué productos, variantes o categorías '
            'se venden más, unidades, ingresos y ganancia bruta por producto. Excluye pedidos '
            'cancelados salvo que se filtre por estado.'
        ),
        'modelo': ItemPedido,
        'tienda': 'tienda',
        'fecha': 'pedido__fecha',
        'estado': 'pedido__estado_actual',
        'dimensiones': {
            **_DIMENSIONES_ITEM,
            'estado': _dim('Estado', ['pedido__estado_actual'], formato=estados.etiqueta),
            **_TIEMPO,
        },
        'metricas': {
            'unidades': _met('Unidades vendidas', ENTERO, lambda: Sum('cantidad'), True),
            'ingresos': _met('Ingresos (Bs)', MONEDA, lambda: Sum(_INGRESOS_ITEM), True),
            'pedidos': _met('Pedidos', ENTERO, lambda: Count('pedido', distinct=True)),
            'precio_promedio': _met('Precio unitario promedio (Bs)', MONEDA, lambda: Avg('precio_unitario')),
            **_METRICAS_GANANCIA,
            'participacion_ingresos': _participacion('Participación en los ingresos (%)', 'ingresos'),
        },
        'texto': {'producto': 'variante__producto__nombre', 'categoria': 'variante__producto__categoria__nombre'},
    },
    'pedidos': {
        'descripcion': (
            'Pedidos completos. Para cantidad de pedidos, monto vendido, ticket promedio, '
            'pedidos por estado o por fecha, y para ranking de clientes (agrupar por cliente). '
            'Excluye pedidos cancelados salvo que se filtre por estado.'
        ),
        'modelo': Pedido,
        'tienda': 'tienda',
        'fecha': 'fecha',
        'estado': 'estado_actual',
        'dimensiones': {
            'tienda': _TIENDA,
            'estado': _dim('Estado', ['estado_actual'], formato=estados.etiqueta),
            'cliente': _dim('Cliente', ['cliente_id', 'cliente__email']),
            **_TIEMPO,
        },
        'metricas': {
            'pedidos': _met('Pedidos', ENTERO, lambda: Count('id'), True),
            'monto_total': _met('Monto total (Bs)', MONEDA, lambda: Sum('total'), True),
            'ticket_promedio': _met('Ticket promedio (Bs)', MONEDA, lambda: Avg('total')),
            'clientes': _met('Clientes distintos', ENTERO, lambda: Count('cliente', distinct=True)),
            'primera_compra': _met('Primera compra', FECHA, lambda: Min('fecha')),
            'ultima_compra': _met('Última compra', FECHA, lambda: Max('fecha')),
        },
        'texto': {'cliente': 'cliente__email'},
    },
    'inventario': {
        'descripcion': (
            'Stock actual del catálogo (variantes de productos activos). Para existencias, '
            'productos con stock bajo o agotados y valor del inventario. No tiene fechas.'
        ),
        'modelo': Variante,
        'tienda': 'producto__tienda',
        'fecha': None,
        'estado': None,
        'base': lambda qs, filtros, tienda_ids: qs.filter(producto__activo=True, activa=True),
        'dimensiones': {**_DIMENSIONES_VARIANTE, 'sku': _dim('SKU', ['sku'])},
        'metricas': {
            'stock': _met('Stock', ENTERO, lambda: Sum('stock'), True),
            'stock_minimo': _met('Stock mínimo', ENTERO, lambda: Sum('stock_minimo'), True),
            'valor_inventario': _met('Valor del inventario (Bs)', MONEDA, lambda: Sum(_VALOR_STOCK), True),
            'precio': _met('Precio (Bs)', MONEDA, lambda: Avg('precio')),
            'variantes': _met('Variantes', ENTERO, lambda: Count('id'), True),
            'productos': _met('Productos', ENTERO, lambda: Count('producto', distinct=True)),
        },
        'texto': {'producto': 'producto__nombre', 'categoria': 'producto__categoria__nombre'},
    },
    'resenas': {
        'descripcion': (
            'Reseñas de clientes. Para calificación promedio, cantidad de reseñas y distribución '
            'de calificaciones 1 a 5 (agrupar por calificacion) por producto o tienda.'
        ),
        'modelo': Resena,
        'tienda': 'tienda',
        'fecha': 'fecha',
        'estado': None,
        'dimensiones': {
            'tienda': _TIENDA,
            'producto': _dim('Producto', ['producto_id', 'producto__nombre']),
            'calificacion': _dim('Calificación', ['calificacion'], tipo=ENTERO),
            'mes': _TIEMPO['mes'],
        },
        'metricas': {
            'resenas': _met('Reseñas', ENTERO, lambda: Count('id'), True),
            'calificacion_promedio': _met('Calificación promedio', DECIMAL, lambda: Avg('calificacion')),
            'positivas': _met('Reseñas positivas (4-5)', ENTERO, lambda: Count('id', filter=Q(calificacion__gte=4)), True),
            'negativas': _met('Reseñas negativas (1-2)', ENTERO, lambda: Count('id', filter=Q(calificacion__lte=2)), True),
            'pct_positivas': _cociente('Reseñas positivas (%)', PORCENTAJE, 'positivas', 'resenas'),
            'pct_negativas': _cociente('Reseñas negativas (%)', PORCENTAJE, 'negativas', 'resenas', mejor_si='baja'),
            'participacion_resenas': _participacion('Participación en el total de reseñas (%)', 'resenas'),
        },
        'texto': {'producto': 'producto__nombre'},
    },
    'pagos': {
        'descripcion': 'Pagos registrados. Para montos cobrados por método de pago (efectivo, tarjeta) o estado del pago.',
        'modelo': Pago,
        'tienda': 'tienda',
        'fecha': 'fecha',
        'estado': None,
        'dimensiones': {
            'tienda': _TIENDA,
            'metodo_pago': _dim('Método de pago', ['metodo_pago__nombre']),
            'estado_pago': _dim('Estado del pago', ['estado']),
            'dia': _TIEMPO['dia'],
            'mes': _TIEMPO['mes'],
        },
        'metricas': {
            'pagos': _met('Pagos', ENTERO, lambda: Count('id'), True),
            'monto': _met('Monto (Bs)', MONEDA, lambda: Sum('monto'), True),
        },
        'texto': {},
    },
    'actividad': {
        'descripcion': (
            'Actividad de los clientes en la tienda: vistas y clics en productos, búsquedas y '
            'agregados al carrito. Para productos más vistos o términos más buscados. Para la '
            'conversión vista a carrito a compra usa `embudo_conversion`.'
        ),
        'modelo': EventoUsuario,
        'tienda': 'tienda',
        'fecha': 'fecha',
        'estado': None,
        'dimensiones': {
            'tienda': _TIENDA,
            'producto': _dim('Producto', ['producto_id', 'producto__nombre']),
            'tipo_evento': _dim('Tipo de evento', ['tipo_evento']),
            'termino_busqueda': _dim('Término buscado', ['termino_busqueda']),
            'dia': _TIEMPO['dia'],
            'mes': _TIEMPO['mes'],
        },
        'metricas': {
            'eventos': _met('Eventos', ENTERO, lambda: Count('id'), True),
            'clientes': _met('Clientes distintos', ENTERO, lambda: Count('cliente', distinct=True)),
        },
        'texto': {'producto': 'producto__nombre'},
    },
    'resultados': {
        'descripcion': (
            'Estado de resultados: ingresos, costo de la mercadería, ganancia bruta, margen bruto, '
            'gastos operativos y utilidad neta (ganancia bruta menos gastos) por tienda o periodo. '
            'Los filtros `producto` y `categoria` acotan las ventas, no los gastos: así responde '
            '"cuánto gané en estos productos descontando gastos". La ganancia solo cuenta ítems '
            'con costo cargado y el resultado informa el % de ventas sin costo. Para ganancia por '
            'producto usa `ventas_productos`; para gastos por categoría, `gastos`.'
        ),
        'componentes': [
            {
                'modelo': ItemPedido, 'tienda': 'tienda', 'fecha': 'pedido__fecha',
                'estado': 'pedido__estado_actual',
                'dimensiones': {**_DIMENSIONES_ITEM, **_TIEMPO},
                'texto': {'producto': 'variante__producto__nombre',
                          'categoria': 'variante__producto__categoria__nombre'},
            },
            {
                'modelo': GastoOperativo, 'tienda': 'tienda', 'fecha': 'fecha', 'fecha_es_date': True,
                'estado': None,
                'dimensiones': {'tienda': _TIENDA, **_TIEMPO},
                'texto': {},
                'avisa_si_filtra': {'producto': _SIN_GASTOS_POR_PRODUCTO, 'categoria': _SIN_GASTOS_POR_PRODUCTO},
            },
        ],
        'metricas': {
            'ingresos': _met('Ingresos (Bs)', MONEDA, lambda: Sum(_INGRESOS_ITEM), True),
            **_METRICAS_GANANCIA,
            'gastos_operativos': _met('Gastos operativos (Bs)', MONEDA, lambda: Sum('monto'), True,
                                      componente=1, mejor_si='baja'),
            'utilidad_neta': _derivada(
                'Utilidad neta (Bs)', MONEDA, ['ganancia_bruta', 'gastos_operativos'],
                lambda v, c: (v['ganancia_bruta'] or 0) - (v['gastos_operativos'] or 0), sumable=True,
                avisa_costo=True),
        },
    },
    'gastos': {
        'descripcion': (
            'Gastos operativos registrados (alquiler, servicios, sueldos, marketing, transporte, '
            'impuestos, otros). Para gastos por categoría, tienda o periodo.'
        ),
        'modelo': GastoOperativo,
        'tienda': 'tienda',
        'fecha': 'fecha',
        'fecha_es_date': True,
        'estado': None,
        'dimensiones': {
            'tienda': _TIENDA,
            'categoria_gasto': _dim('Categoría de gasto', ['categoria'],
                                    formato=lambda v: dict(GastoOperativo.Categoria.choices).get(v, v)),
            **_TIEMPO,
        },
        'metricas': {
            'gastos': _met('Gastos operativos (Bs)', MONEDA, lambda: Sum('monto'), True, mejor_si='baja'),
            'registros': _met('Gastos registrados', ENTERO, lambda: Count('id'), True),
            'gasto_promedio': _met('Gasto promedio (Bs)', MONEDA, lambda: Avg('monto')),
        },
        'texto': {},
    },
    'cancelaciones': {
        'descripcion': (
            'Pedidos incluyendo los cancelados. Para la tasa de cancelación (% de pedidos '
            'cancelados) y el monto perdido, por tienda, estado o periodo.'
        ),
        'modelo': Pedido,
        'tienda': 'tienda',
        'fecha': 'fecha',
        'estado': 'estado_actual',
        'incluye_cancelados': True,
        'dimensiones': {
            'tienda': _TIENDA,
            'estado': _dim('Estado', ['estado_actual'], formato=estados.etiqueta),
            **_TIEMPO,
        },
        'metricas': {
            'pedidos': _met('Pedidos (con cancelados)', ENTERO, lambda: Count('id'), True),
            'cancelados': _met('Pedidos cancelados', ENTERO,
                               lambda: Count('id', filter=Q(estado_actual=estados.CANCELADO)), True,
                               mejor_si='baja'),
            'tasa_cancelacion': _cociente('Tasa de cancelación (%)', PORCENTAJE, 'cancelados', 'pedidos',
                                          mejor_si='baja'),
            'monto_cancelado': _met('Monto cancelado (Bs)', MONEDA,
                                    lambda: Sum('total', filter=Q(estado_actual=estados.CANCELADO)), True,
                                    mejor_si='baja'),
        },
        'texto': {},
    },
    'clientes': {
        'descripcion': (
            'Clientes nuevos vs recurrentes y tasa de recompra. Un cliente es nuevo si su primera '
            'compra (en las tiendas consultadas) cae dentro del periodo, y recurrente si ya había '
            'comprado antes. Necesita fecha_desde y fecha_hasta. Solo se puede agrupar por tienda.'
        ),
        'requiere_periodo': True,
        'modelo': Pedido,
        'tienda': 'tienda',
        'fecha': 'fecha',
        'estado': 'estado_actual',
        'base': _base_clientes,
        'dimensiones': {'tienda': _TIENDA},
        'metricas': {
            'clientes': _met('Clientes activos', ENTERO, lambda: Count('cliente', distinct=True)),
            'clientes_nuevos': _met('Clientes nuevos', ENTERO,
                                    lambda: Count('cliente', distinct=True, filter=Q(_es_nuevo=True))),
            'clientes_recurrentes': _met('Clientes recurrentes', ENTERO,
                                         lambda: Count('cliente', distinct=True, filter=Q(_es_nuevo=False))),
            'tasa_recompra': _cociente('Tasa de recompra (%)', PORCENTAJE, 'clientes_recurrentes', 'clientes'),
            'pedidos': _met('Pedidos', ENTERO, lambda: Count('id')),
            'pedidos_por_cliente': _cociente('Pedidos por cliente', DECIMAL, 'pedidos', 'clientes', factor=1),
        },
        'texto': {},
    },
    'embudo_conversion': {
        'descripcion': (
            'Embudo de conversión: vistas de producto, agregados al carrito y compras (pedidos no '
            'cancelados) con sus tasas vista a carrito, carrito a compra y vista a compra. Cuenta '
            'eventos, no personas únicas. Se agrupa por tienda o periodo.'
        ),
        'componentes': [
            {
                'modelo': EventoUsuario, 'tienda': 'tienda', 'fecha': 'fecha', 'estado': None,
                'dimensiones': {'tienda': _TIENDA, **_TIEMPO}, 'texto': {},
            },
            {
                'modelo': Pedido, 'tienda': 'tienda', 'fecha': 'fecha', 'estado': 'estado_actual',
                'dimensiones': {'tienda': _TIENDA, **_TIEMPO}, 'texto': {},
            },
        ],
        'metricas': {
            'vistas': _met('Vistas de producto', ENTERO, lambda: Count('id', filter=Q(tipo_evento='VIEW')), True),
            'carritos': _met('Agregados al carrito', ENTERO, lambda: Count('id', filter=Q(tipo_evento='CART')), True),
            'compras': _met('Compras (pedidos)', ENTERO, lambda: Count('id'), True, componente=1),
            'tasa_vista_a_carrito': _cociente('Vista a carrito (%)', PORCENTAJE, 'carritos', 'vistas'),
            'tasa_carrito_a_compra': _cociente('Carrito a compra (%)', PORCENTAJE, 'compras', 'carritos'),
            'tasa_vista_a_compra': _cociente('Vista a compra (%)', PORCENTAJE, 'compras', 'vistas'),
        },
    },
    'entregas': {
        'descripcion': (
            'Tiempo de entrega de los pedidos entregados, medido en el historial de estados desde '
            'que el pedido quedó pendiente hasta que pasó a entregado. El periodo se filtra por '
            'la fecha de creación del pedido.'
        ),
        'modelo': Pedido,
        'tienda': 'tienda',
        'fecha': 'fecha',
        'estado': None,
        'base': _base_entregas,
        'dimensiones': {'tienda': _TIENDA, **_TIEMPO},
        'metricas': {
            'entregados': _met('Pedidos entregados', ENTERO, lambda: Count('id'), True),
            'horas_entrega_promedio': _met('Tiempo de entrega promedio (horas)', DECIMAL,
                                           lambda: Avg('_duracion'), unidad_segundos=3600, mejor_si='baja'),
            'dias_entrega_promedio': _met('Tiempo de entrega promedio (días)', DECIMAL,
                                          lambda: Avg('_duracion'), unidad_segundos=86400, mejor_si='baja'),
            'horas_entrega_maxima': _met('Entrega más lenta (horas)', DECIMAL,
                                         lambda: Max('_duracion'), unidad_segundos=3600, mejor_si='baja'),
            'horas_entrega_minima': _met('Entrega más rápida (horas)', DECIMAL,
                                         lambda: Min('_duracion'), unidad_segundos=3600),
        },
        'texto': {},
    },
    'rotacion_inventario': {
        'descripcion': (
            'Rotación de inventario por producto, variante, categoría o tienda: unidades vendidas '
            'en el periodo contra el stock actual (veces) y días de inventario (cuántos días dura '
            'el stock al ritmo de venta del periodo). Necesita fecha_desde y fecha_hasta. Solo '
            'productos activos.'
        ),
        'requiere_periodo': True,
        'componentes': [
            {
                'modelo': Variante, 'tienda': 'producto__tienda', 'fecha': None, 'estado': None,
                'base': lambda qs, filtros, tienda_ids: qs.filter(producto__activo=True, activa=True),
                'dimensiones': _DIMENSIONES_VARIANTE,
                'texto': {'producto': 'producto__nombre', 'categoria': 'producto__categoria__nombre'},
            },
            {
                'modelo': ItemPedido, 'tienda': 'tienda', 'fecha': 'pedido__fecha',
                'estado': 'pedido__estado_actual',
                'dimensiones': _DIMENSIONES_ITEM,
                'texto': {'producto': 'variante__producto__nombre',
                          'categoria': 'variante__producto__categoria__nombre'},
            },
        ],
        'metricas': {
            'stock_actual': _met('Stock actual', ENTERO, lambda: Sum('stock'), True),
            'unidades_vendidas': _met('Unidades vendidas en el periodo', ENTERO, lambda: Sum('cantidad'), True,
                                      componente=1),
            'rotacion': _cociente('Rotación (veces)', DECIMAL, 'unidades_vendidas', 'stock_actual', factor=1),
            'dias_de_inventario': _derivada(
                'Días de inventario', DECIMAL, ['stock_actual', 'unidades_vendidas'],
                lambda v, c: v['stock_actual'] * c['dias_periodo'] / v['unidades_vendidas']
                if v['unidades_vendidas'] and v['stock_actual'] else None),
        },
    },
    'carritos_recuperados': {
        'descripcion': (
            'Campaña de recuperación de carritos abandonados: notificaciones enviadas, carritos '
            'recuperados (el cliente terminó comprando), tasa de recuperación e ingresos recuperados.'
        ),
        'modelo': RegistroRecuperacionCarrito,
        'tienda': 'campana__tienda',
        'fecha': 'fecha_envio',
        'estado': None,
        'dimensiones': {
            'tienda': _dim('Tienda', ['campana__tienda_id', 'campana__tienda__nombre']),
            **_TIEMPO,
        },
        'metricas': {
            'notificaciones': _met('Notificaciones enviadas', ENTERO, lambda: Count('id'), True),
            'recuperados': _met('Carritos recuperados', ENTERO, lambda: Count('id', filter=Q(recuperado=True)), True),
            'tasa_recuperacion': _cociente('Tasa de recuperación (%)', PORCENTAJE, 'recuperados', 'notificaciones'),
            'ingresos_recuperados': _met('Ingresos recuperados (Bs)', MONEDA,
                                         lambda: Sum('pedido_resultante__total', filter=Q(recuperado=True)), True),
        },
        'texto': {},
    },
    'cupones': {
        'descripcion': (
            'Uso de cupones: veces usados, pedidos con cupón, ventas con cupón y qué % de los pedidos '
            'usó cupón. Se agrupa por cupón (sin la tasa de uso), tienda o periodo.'
        ),
        'componentes': [
            {
                'modelo': CuponUso, 'tienda': 'tienda', 'fecha': 'fecha_uso', 'estado': 'pedido__estado_actual',
                'dimensiones': {'tienda': _TIENDA, 'cupon': _dim('Cupón', ['cupon_id', 'cupon__codigo']), **_TIEMPO},
                'texto': {},
            },
            {
                'modelo': Pedido, 'tienda': 'tienda', 'fecha': 'fecha', 'estado': 'estado_actual',
                'dimensiones': {'tienda': _TIENDA, **_TIEMPO}, 'texto': {},
            },
        ],
        'metricas': {
            'usos': _met('Usos de cupón', ENTERO, lambda: Count('id'), True),
            'pedidos_con_cupon': _met('Pedidos con cupón', ENTERO, lambda: Count('pedido', distinct=True)),
            'ventas_con_cupon': _met('Ventas con cupón (Bs)', MONEDA, lambda: Sum('pedido__total'), True),
            'pedidos_totales': _met('Pedidos totales', ENTERO, lambda: Count('id'), True, componente=1),
            'tasa_uso_cupon': _cociente('Pedidos con cupón (%)', PORCENTAJE, 'pedidos_con_cupon', 'pedidos_totales'),
        },
    },
}

FILTROS = {
    'fecha_desde': 'Fecha inicial inclusive, AAAA-MM-DD.',
    'fecha_hasta': 'Fecha final inclusive, AAAA-MM-DD.',
    'estados': f'Estados de pedido: {", ".join(ESTADOS_PEDIDO)}. Por defecto todos menos cancelado.',
    'tienda_ids': 'Ids de tiendas (solo de las permitidas).',
    'producto': 'Texto contenido en el nombre del producto.',
    'categoria': 'Texto contenido en el nombre de la categoría.',
    'cliente': 'Texto contenido en el email del cliente.',
    'solo_stock_bajo': 'Solo variantes con stock menor o igual al stock mínimo (inventario).',
    'solo_agotados': 'Solo variantes con stock 0 (inventario).',
    'tipo_evento': 'VIEW, CLICK, SEARCH o CART (actividad).',
    'metodo_pago': 'Texto contenido en el nombre del método de pago (pagos).',
}


def _componentes(fuente):
    return fuente.get('componentes') or [fuente]


def _dimensiones(fuente):
    return {dim: definicion for comp in _componentes(fuente) for dim, definicion in comp['dimensiones'].items()}


def _tiene_fecha(fuente):
    return any(comp['fecha'] for comp in _componentes(fuente))


def _tiene_estado(fuente):
    return any(comp['estado'] for comp in _componentes(fuente))


def catalogo_para_modelo():
    """Descripción compacta de las fuentes, para el prompt del sistema."""
    lineas = []
    for clave, fuente in FUENTES.items():
        lineas.append(f'- `{clave}`: {fuente["descripcion"]}')
        lineas.append(f'  - agrupar_por: {", ".join(_dimensiones(fuente))}')
        lineas.append('  - metricas: ' + ', '.join(
            f'{m} ({d["titulo"]})' if d['tipo'] in (PORCENTAJE, DECIMAL) or d.get('avisa_costo') else m
            for m, d in fuente['metricas'].items()))
    lineas.append('- Filtros (todos opcionales):')
    for clave, texto in FILTROS.items():
        lineas.append(f'  - `{clave}`: {texto}')
    return '\n'.join(lineas)


ESQUEMA_ESPECIFICACION = {
    'type': 'object',
    'properties': {
        'fuente': {'type': 'string', 'enum': list(FUENTES)},
        'agrupar_por': {
            'type': 'array', 'items': {'type': 'string'}, 'maxItems': MAX_AGRUPAR,
            'description': 'Columnas para agrupar (las de la fuente). Vacío = una sola fila de totales.',
        },
        'metricas': {
            'type': 'array', 'items': {'type': 'string'}, 'minItems': 1, 'maxItems': MAX_METRICAS,
            'description': 'Métricas de la fuente a calcular.',
        },
        'filtros': {
            'type': 'object',
            'properties': {
                'fecha_desde': {'type': 'string'},
                'fecha_hasta': {'type': 'string'},
                'estados': {'type': 'array', 'items': {'type': 'string', 'enum': ESTADOS_PEDIDO}},
                'tienda_ids': {'type': 'array', 'items': {'type': 'integer'}},
                'producto': {'type': 'string'},
                'categoria': {'type': 'string'},
                'cliente': {'type': 'string'},
                'solo_stock_bajo': {'type': 'boolean'},
                'solo_agotados': {'type': 'boolean'},
                'tipo_evento': {'type': 'string', 'enum': ['VIEW', 'CLICK', 'SEARCH', 'CART']},
                'metodo_pago': {'type': 'string'},
            },
            'additionalProperties': False,
        },
        'comparar_con': {
            'type': 'string', 'enum': list(COMPARACIONES),
            'description': (
                'Compara el periodo de fecha_desde/fecha_hasta (obligatorias) con otro: el de igual '
                'duración justo antes (`periodo_anterior`) o las mismas fechas del año pasado '
                '(`mismo_periodo_anio_anterior`). Cada métrica devuelve además `<metrica>_anterior` y '
                '`<metrica>_variacion` (% de cambio; en puntos si la métrica ya es un %). Máx. '
                f'{MAX_METRICAS_COMPARANDO} métricas y sin agrupar por día/semana/mes.'
            ),
        },
        'ordenar_por': {
            'type': 'string',
            'description': (
                'Una métrica o columna de agrupar_por (o `<metrica>_variacion` al comparar). Por '
                'defecto el tiempo si se agrupa por fecha, o si no la primera métrica.'
            ),
        },
        'descendente': {
            'type': 'boolean',
            'description': (
                'Orden descendente. Por defecto true para métricas y false para columnas de agrupar '
                '(fechas en orden cronológico ascendente). Ponlo en true solo si piden lo más reciente primero.'
            ),
        },
        'limite': {'type': 'integer', 'minimum': 1, 'maximum': MAX_FILAS},
    },
    'required': ['fuente', 'metricas'],
    'additionalProperties': False,
}


# ---------------------------------------------------------------------------
# Ejecución
# ---------------------------------------------------------------------------

def _fecha(valor, campo):
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError as exc:
        raise ConsultaInvalida(f'`{campo}` debe tener el formato AAAA-MM-DD.') from exc


def _inicio_del_dia(dia):
    return timezone.make_aware(datetime.combine(dia, datetime.min.time()))


def _lista(valor):
    if valor is None:
        return []
    return list(valor) if isinstance(valor, (list, tuple)) else [valor]


def _con_dependencias(definiciones, claves):
    """Las métricas pedidas más las que necesitan para calcularse, dependencias primero."""
    orden = []

    def visitar(clave):
        if clave in orden:
            return
        for dependencia in definiciones[clave].get('depende', []):
            visitar(dependencia)
        orden.append(clave)

    for clave in claves:
        visitar(clave)
    return orden


def normalizar(spec):
    """Valida la especificación y la devuelve completa con sus valores por defecto."""
    if not isinstance(spec, dict):
        raise ConsultaInvalida('La consulta debe ser un objeto.')
    fuente_clave = spec.get('fuente')
    if fuente_clave not in FUENTES:
        raise ConsultaInvalida(f'Fuente desconocida. Usa una de: {", ".join(FUENTES)}.')
    fuente = FUENTES[fuente_clave]
    dimensiones = _dimensiones(fuente)

    agrupar = []
    for dim in _lista(spec.get('agrupar_por')):
        if dim not in dimensiones:
            raise ConsultaInvalida(
                f'`{dim}` no se puede agrupar en {fuente_clave}. Opciones: {", ".join(dimensiones)}.')
        if dim not in agrupar:
            agrupar.append(dim)
    if len(agrupar) > MAX_AGRUPAR:
        raise ConsultaInvalida(f'Agrupa por {MAX_AGRUPAR} columnas como máximo.')

    metricas = []
    for met in _lista(spec.get('metricas')):
        if met not in fuente['metricas']:
            raise ConsultaInvalida(
                f'`{met}` no es una métrica de {fuente_clave}. Opciones: {", ".join(fuente["metricas"])}.')
        if met not in metricas:
            metricas.append(met)
    if not metricas:
        raise ConsultaInvalida('Pide al menos una métrica.')
    if len(metricas) > MAX_METRICAS:
        raise ConsultaInvalida(f'Pide {MAX_METRICAS} métricas como máximo.')

    for met in _con_dependencias(fuente['metricas'], metricas):
        definicion = fuente['metricas'][met]
        if not definicion['expr']:
            continue
        soportadas = _componentes(fuente)[definicion['componente']]['dimensiones']
        faltan = [d for d in agrupar if d not in soportadas]
        if faltan:
            raise ConsultaInvalida(
                f'`{met}` no se puede desglosar por {", ".join(faltan)} en {fuente_clave}. '
                f'Con esa métrica agrupa solo por: {", ".join(soportadas)}.')

    filtros = spec.get('filtros') or {}
    if not isinstance(filtros, dict):
        raise ConsultaInvalida('`filtros` debe ser un objeto.')
    # El modelo a veces pone los filtros al nivel superior ("fecha_desde" junto
    # a "fuente"). Ignorarlos en silencio daba informes de todo el historial
    # rotulados como "últimos 30 días"; se mueven a `filtros`.
    filtros = dict(filtros)
    claves_validas = set(ESQUEMA_ESPECIFICACION['properties'])
    for clave in set(spec) - claves_validas:
        if clave not in FILTROS:
            raise ConsultaInvalida(f'Campo desconocido: `{clave}`. Los filtros van dentro de `filtros`.')
        filtros.setdefault(clave, spec[clave])
    desconocidos = set(filtros) - set(FILTROS)
    if desconocidos:
        raise ConsultaInvalida(f'Filtros desconocidos: {", ".join(sorted(desconocidos))}.')
    if not _tiene_fecha(fuente) and (filtros.get('fecha_desde') or filtros.get('fecha_hasta')):
        raise ConsultaInvalida(f'La fuente {fuente_clave} no tiene fechas; quita el filtro de fecha.')
    for estado in _lista(filtros.get('estados')):
        if estado not in ESTADOS_PEDIDO and estado != estados.COMPLETADO_LEGADO:
            raise ConsultaInvalida(f'Estado desconocido: {estado}.')
    desde = _fecha(filtros['fecha_desde'], 'fecha_desde') if filtros.get('fecha_desde') else None
    hasta = _fecha(filtros['fecha_hasta'], 'fecha_hasta') if filtros.get('fecha_hasta') else None
    if desde and hasta and desde > hasta:
        raise ConsultaInvalida('`fecha_desde` no puede ser posterior a `fecha_hasta`.')
    if fuente.get('requiere_periodo') and not (desde and hasta):
        raise ConsultaInvalida(f'La fuente {fuente_clave} necesita `fecha_desde` y `fecha_hasta`.')

    comparar_con = spec.get('comparar_con') or None
    if comparar_con:
        if comparar_con not in COMPARACIONES:
            raise ConsultaInvalida(f'`comparar_con` debe ser una de: {", ".join(COMPARACIONES)}.')
        if not (desde and hasta):
            raise ConsultaInvalida('Para comparar periodos pon `fecha_desde` y `fecha_hasta` en `filtros`.')
        if len(metricas) > MAX_METRICAS_COMPARANDO:
            raise ConsultaInvalida(f'Al comparar periodos pide {MAX_METRICAS_COMPARANDO} métricas como máximo.')
        tiempo = [d for d in agrupar if 'trunc' in dimensiones[d]]
        if tiempo:
            raise ConsultaInvalida(
                f'No se puede comparar periodos agrupando por {", ".join(tiempo)}: quita esa columna o la comparación.')
        fechas = [m for m in metricas if fuente['metricas'][m]['tipo'] == FECHA]
        if fechas:
            raise ConsultaInvalida(f'`{fechas[0]}` es una fecha y no se puede comparar entre periodos.')

    ordenar_por = spec.get('ordenar_por') or None
    validas = set(agrupar) | set(metricas)
    if comparar_con:
        validas |= {f'{m}{sufijo}' for m in metricas for sufijo in ('_anterior', '_variacion')}
    if ordenar_por and ordenar_por not in validas:
        raise ConsultaInvalida('`ordenar_por` debe ser una de las métricas o columnas pedidas.')

    try:
        limite = int(spec.get('limite') or LIMITE_POR_DEFECTO)
    except (TypeError, ValueError) as exc:
        raise ConsultaInvalida('`limite` debe ser un número.') from exc

    return {
        'fuente': fuente_clave,
        'agrupar_por': agrupar,
        'metricas': metricas,
        'filtros': filtros,
        'comparar_con': comparar_con,
        'ordenar_por': ordenar_por,
        'descendente': spec.get('descendente'),
        'limite': max(1, min(limite, MAX_FILAS)),
    }


def _hace_un_anio(dia):
    try:
        return dia.replace(year=dia.year - 1)
    except ValueError:  # 29 de febrero
        return dia.replace(year=dia.year - 1, day=28)


def _periodo_comparado(filtros, modo):
    desde = _fecha(filtros['fecha_desde'], 'fecha_desde')
    hasta = _fecha(filtros['fecha_hasta'], 'fecha_hasta')
    if modo == 'mismo_periodo_anio_anterior':
        return _hace_un_anio(desde), _hace_un_anio(hasta)
    dias = (hasta - desde).days + 1
    hasta_anterior = desde - timedelta(days=1)
    return hasta_anterior - timedelta(days=dias - 1), hasta_anterior


def _contexto(filtros):
    if not (filtros.get('fecha_desde') and filtros.get('fecha_hasta')):
        return {'dias_periodo': None}
    dias = (_fecha(filtros['fecha_hasta'], 'fecha_hasta') - _fecha(filtros['fecha_desde'], 'fecha_desde')).days + 1
    return {'dias_periodo': dias}


def _aplicar_filtros(qs, comp, filtros, tienda_ids):
    qs = qs.filter(**{f'{comp["tienda"]}__in': tienda_ids})

    if comp['fecha']:
        desde = _fecha(filtros['fecha_desde'], 'fecha_desde') if filtros.get('fecha_desde') else None
        hasta = _fecha(filtros['fecha_hasta'], 'fecha_hasta') if filtros.get('fecha_hasta') else None
        # Los campos DateField se comparan con fechas; los DateTimeField, con el
        # inicio de cada día en la zona horaria del proyecto.
        if comp.get('fecha_es_date'):
            if desde:
                qs = qs.filter(**{f'{comp["fecha"]}__gte': desde})
            if hasta:
                qs = qs.filter(**{f'{comp["fecha"]}__lte': hasta})
        else:
            if desde:
                qs = qs.filter(**{f'{comp["fecha"]}__gte': _inicio_del_dia(desde)})
            if hasta:
                qs = qs.filter(**{f'{comp["fecha"]}__lt': _inicio_del_dia(hasta + timedelta(days=1))})

    if comp['estado']:
        pedidos = _lista(filtros.get('estados'))
        if pedidos:
            # `completado` es el nombre viejo de `pendiente` (CU-22).
            if estados.PENDIENTE in pedidos:
                pedidos.append(estados.COMPLETADO_LEGADO)
            qs = qs.filter(**{f'{comp["estado"]}__in': pedidos})
        elif not comp.get('incluye_cancelados'):
            qs = qs.exclude(**{comp['estado']: estados.CANCELADO})

    for filtro, campo in comp.get('texto', {}).items():
        valor = str(filtros.get(filtro) or '').strip()
        if valor:
            qs = qs.filter(**{f'{campo}__icontains': valor})

    if comp['modelo'] is Variante:
        if filtros.get('solo_stock_bajo'):
            qs = qs.filter(stock__lte=F('stock_minimo'))
        if filtros.get('solo_agotados'):
            qs = qs.filter(stock=0)
    if comp['modelo'] is EventoUsuario and filtros.get('tipo_evento'):
        qs = qs.filter(tipo_evento=filtros['tipo_evento'])
    if comp['modelo'] is Pago and filtros.get('metodo_pago'):
        qs = qs.filter(metodo_pago__nombre__icontains=str(filtros['metodo_pago']))
    return qs


def _valor(valor, tipo, dim=None):
    """Convierte un valor del ORM a algo serializable en JSON."""
    if valor is None:
        return None
    if tipo == FECHA:
        if isinstance(valor, datetime):
            valor = timezone.localtime(valor) if timezone.is_aware(valor) else valor
        if dim == 'mes':
            return valor.strftime('%Y-%m')
        if dim in ('dia', 'semana'):
            return (valor.date() if isinstance(valor, datetime) else valor).isoformat()
        return valor.strftime('%Y-%m-%d %H:%M') if isinstance(valor, datetime) else valor.isoformat()
    if tipo == ENTERO:
        return int(valor)
    if tipo in (MONEDA, DECIMAL, PORCENTAJE, VARIACION, PUNTOS):
        return float(Decimal(valor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    return str(valor)


def _crudo(valor, definicion):
    """Valor de la base como `Decimal` (o fecha), para operar sin mezclar tipos."""
    if valor is None or definicion['tipo'] == FECHA:
        return valor
    if isinstance(valor, timedelta):
        return Decimal(str(valor.total_seconds())) / definicion['unidad_segundos']
    return Decimal(str(valor))


def _celda(definicion, registro, dim):
    if 'trunc' in definicion:
        return _valor(registro[f'_t_{dim}'], FECHA, dim)
    if definicion['mostrar'] == '__variante__':
        producto, variante = registro[definicion['campos'][1]], registro[definicion['campos'][2]]
        return f'{producto} — {variante}' if variante else str(producto)
    valor = registro[definicion['mostrar']]
    if valor is None:
        return '(sin dato)'
    return definicion['formato'](valor) if definicion['formato'] else _valor(valor, definicion['tipo'])


def _agregar_componente(comp, agrupar, filtros, tienda_ids, claves, definiciones):
    """Agrupa y agrega un componente. Devuelve `[(clave de grupo, celdas, {metrica: valor})]`."""
    qs = comp['modelo'].objects.all()
    if 'base' in comp:
        qs = comp['base'](qs, filtros, tienda_ids)
    qs = _aplicar_filtros(qs, comp, filtros, tienda_ids)
    agregados = {f'_m_{m}': definiciones[m]['expr']() for m in claves}

    def valores(registro):
        return {m: _crudo(registro[f'_m_{m}'], definiciones[m]) for m in claves}

    if not agrupar:
        return [((), [], valores(qs.aggregate(**agregados)))]

    campos, tiempos = [], {}
    for dim in agrupar:
        definicion = comp['dimensiones'][dim]
        if 'trunc' in definicion:
            tiempos[f'_t_{dim}'] = definicion['trunc'](comp['fecha'])
            campos.append(f'_t_{dim}')
        else:
            campos.extend(c for c in definicion['campos'] if c not in campos)
    if tiempos:
        qs = qs.annotate(**tiempos)

    filas = []
    for registro in qs.values(*campos).annotate(**agregados).order_by():
        celdas = [_celda(comp['dimensiones'][dim], registro, dim) for dim in agrupar]
        # Los grupos de tiempo se identifican por su etiqueta (los componentes
        # pueden fechar con DateField o DateTimeField); el resto, por sus campos.
        clave = tuple(
            celda if 'trunc' in comp['dimensiones'][dim]
            else tuple(registro[c] for c in comp['dimensiones'][dim]['campos'])
            for dim, celda in zip(agrupar, celdas))
        filas.append((clave, celdas, valores(registro)))
    return filas


def _calcular(fuente, agrupar, filtros, tienda_ids, metricas):
    """Agrega cada componente, junta sus filas por grupo y calcula las derivadas.

    `metricas` ya incluye las dependencias. Devuelve `{clave: {'celdas', 'valores'}}`.
    """
    definiciones = fuente['metricas']
    grupos = {} if agrupar else {(): {'celdas': [], 'valores': {}}}
    for indice, comp in enumerate(_componentes(fuente)):
        claves = [m for m in metricas if definiciones[m]['expr'] and definiciones[m]['componente'] == indice]
        if not claves:
            continue
        for clave, celdas, valores in _agregar_componente(comp, agrupar, filtros, tienda_ids, claves, definiciones):
            grupos.setdefault(clave, {'celdas': celdas, 'valores': {}})['valores'].update(valores)

    contexto = _contexto(filtros)
    for grupo in grupos.values():
        valores = grupo['valores']
        for met in metricas:
            if definiciones[met]['expr']:
                valores.setdefault(met, None)
        for met in metricas:
            if definiciones[met].get('formula'):
                valores[met] = definiciones[met]['formula'](valores, contexto)

    for met in metricas:
        base = definiciones[met].get('participacion')
        if not base:
            continue
        total = sum((g['valores'][base] or 0 for g in grupos.values()), Decimal(0))
        for grupo in grupos.values():
            grupo['valores'][met] = (grupo['valores'][base] or 0) * 100 / total if total else None
    return grupos


def _variacion(actual, anterior, tipo):
    if actual is None or anterior is None:
        return None
    if tipo == PORCENTAJE:
        return actual - anterior
    if not anterior:
        return None
    return (actual - anterior) / abs(anterior) * 100


def _sin_vacios(valor, tipo):
    """Un conteo o monto sin filas vale 0; el resto (promedios, cocientes) queda sin dato."""
    return Decimal(0) if valor is None and tipo in (ENTERO, MONEDA) else valor


def _columnas_de_metrica(met, definicion, comparar_con):
    columna = {'clave': met, 'titulo': definicion['titulo'], 'tipo': definicion['tipo'],
               'sumable': definicion['sumable']}
    if definicion.get('mejor_si'):
        columna['mejor_si'] = definicion['mejor_si']
    if not comparar_con:
        return [columna]
    es_porcentaje = definicion['tipo'] == PORCENTAJE
    anterior = {**columna, 'clave': f'{met}_anterior', 'titulo': f'{definicion["titulo"]} · {COMPARACIONES[comparar_con]}'}
    variacion = {
        'clave': f'{met}_variacion',
        'titulo': f'{definicion["titulo"]} · variación ({"puntos" if es_porcentaje else "%"})',
        'tipo': PUNTOS if es_porcentaje else VARIACION, 'sumable': False,
    }
    if definicion.get('mejor_si'):
        variacion['mejor_si'] = definicion['mejor_si']
    return [columna, anterior, variacion]


def _ordenar(filas, clave, descendente):
    """Ordena por una columna dejando los vacíos al final, con desempate estable por las celdas."""
    filas = sorted(filas, key=lambda f: [str(c) for c in f['celdas']])
    con_valor = [f for f in filas if f['mapa'][clave] is not None]
    sin_valor = [f for f in filas if f['mapa'][clave] is None]
    con_valor.sort(key=lambda f: f['mapa'][clave], reverse=descendente)
    return con_valor + sin_valor


def _nota_costo(fuente, spec, tienda_ids):
    if not any(fuente['metricas'][m].get('avisa_costo') for m in spec['metricas']):
        return []
    metricas = ['ingresos', 'ingresos_sin_costo']
    total = _calcular(fuente, [], spec['filtros'], tienda_ids, metricas)[()]['valores']
    ingresos, sin_costo = total['ingresos'] or 0, total['ingresos_sin_costo'] or 0
    if not ingresos:
        return []
    if not sin_costo:
        return ['Todas las ventas del periodo tienen costo cargado.']
    porcentaje = sin_costo * 100 / ingresos
    if porcentaje >= 100:
        return ['Ninguna venta del periodo tiene costo cargado: la ganancia y el margen no se pueden calcular.']
    return [
        f'El {porcentaje:.1f} % de las ventas (Bs {sin_costo:.2f} de Bs {ingresos:.2f}) no tiene costo cargado. '
        'Esas ventas no entran en el costo, la ganancia ni el margen, que cubren solo el resto.'
    ]


def ejecutar(spec, tienda_ids):
    """Corre una especificación ya normalizada sobre las tiendas indicadas.

    Devuelve `{columnas, filas, total_filas, truncado, notas}`; `filas` es una
    lista de listas en el orden de `columnas` y `notas` son avisos que deben
    acompañar la tabla (comparación usada, ventas sin costo, filtros que no
    aplican a una parte de los datos).
    """
    fuente = FUENTES[spec['fuente']]
    definiciones = fuente['metricas']
    tienda_ids = list(tienda_ids)
    filtros = spec['filtros']
    agrupar, metricas = spec['agrupar_por'], spec['metricas']
    necesarias = _con_dependencias(definiciones, metricas)

    actuales = _calcular(fuente, agrupar, filtros, tienda_ids, necesarias)
    notas = []
    anteriores = None
    if spec['comparar_con']:
        desde, hasta = _periodo_comparado(filtros, spec['comparar_con'])
        filtros_anteriores = {**filtros, 'fecha_desde': desde.isoformat(), 'fecha_hasta': hasta.isoformat()}
        anteriores = _calcular(fuente, agrupar, filtros_anteriores, tienda_ids, necesarias)
        notas.append(
            f'Comparación con el {COMPARACIONES[spec["comparar_con"]]} ({desde.isoformat()} a {hasta.isoformat()}). '
            'Las filas son las que tuvieron actividad en el periodo actual; una variación vacía significa que '
            'el periodo anterior no tiene base (valor 0 o sin dato).')

    usados = {definiciones[m]['componente'] for m in necesarias if definiciones[m]['expr']}
    for indice in sorted(usados):
        for filtro, aviso in _componentes(fuente)[indice].get('avisa_si_filtra', {}).items():
            if filtros.get(filtro) and aviso not in notas:
                notas.append(aviso)
    notas.extend(_nota_costo(fuente, spec, tienda_ids))

    dimensiones = _dimensiones(fuente)
    columnas = [
        {'clave': dim, 'titulo': dimensiones[dim]['etiqueta'], 'tipo': dimensiones[dim]['tipo'], 'sumable': False}
        for dim in agrupar]
    for met in metricas:
        columnas.extend(_columnas_de_metrica(met, definiciones[met], spec['comparar_con']))

    filas = []
    for clave, grupo in actuales.items():
        mapa = dict(zip(agrupar, grupo['celdas']))
        for met in metricas:
            tipo = definiciones[met]['tipo']
            actual = _sin_vacios(grupo['valores'][met], tipo)
            mapa[met] = actual
            if anteriores is not None:
                previo = anteriores.get(clave)
                anterior = _sin_vacios(previo['valores'][met] if previo else None, tipo)
                mapa[f'{met}_anterior'] = anterior
                mapa[f'{met}_variacion'] = _variacion(actual, anterior, tipo)
        filas.append({'celdas': grupo['celdas'], 'mapa': mapa})

    if agrupar:
        clave_orden = spec['ordenar_por'] or next(
            (d for d in agrupar if 'trunc' in dimensiones[d]), metricas[0])
        descendente = spec['descendente']
        if descendente is None:
            descendente = clave_orden not in agrupar
        filas = _ordenar(filas, clave_orden, descendente)

    total_filas = len(filas)
    filas = filas[:spec['limite']]
    tipos = {c['clave']: c['tipo'] for c in columnas}
    return {
        'columnas': columnas,
        'filas': [[
            fila['mapa'][c['clave']] if c['clave'] in agrupar else _valor(fila['mapa'][c['clave']], tipos[c['clave']])
            for c in columnas] for fila in filas],
        'total_filas': total_filas,
        'truncado': total_filas > len(filas),
        'notas': notas,
    }


def resumen_para_modelo(resultado, spec=None):
    """Lo que el modelo necesita para analizar, sin mandarle cientos de filas."""
    columnas = resultado['columnas']
    filas = resultado['filas']
    totales = {}
    for i, col in enumerate(columnas):
        if col.get('sumable') and filas:
            totales[col['clave']] = round(sum(f[i] or 0 for f in filas), 2)
    resumen = {}
    if spec is not None:
        # Se le devuelve lo que realmente se filtró para que el análisis no
        # hable de un periodo que la consulta no aplicó.
        resumen['filtros_aplicados'] = describir_filtros(spec, {}) or 'ninguno'
    if resultado.get('notas'):
        resumen['notas'] = resultado['notas']
    return {
        **resumen,
        'columnas': [f'{c["clave"]} ({c["titulo"]})' for c in columnas],
        'filas': filas[:MAX_FILAS_PARA_MODELO],
        'filas_en_tabla': len(filas),
        'total_filas_que_cumplen': resultado['total_filas'],
        'filas_omitidas_para_ti': max(0, len(filas) - MAX_FILAS_PARA_MODELO),
        'totales_de_la_tabla': totales,
    }


def describir_filtros(spec, tiendas_por_id):
    """Texto legible de los filtros aplicados, para el encabezado del informe."""
    filtros = spec['filtros']
    fuente = FUENTES[spec['fuente']]
    partes = []
    if filtros.get('fecha_desde') or filtros.get('fecha_hasta'):
        partes.append(f'Periodo: {filtros.get("fecha_desde") or "inicio"} a {filtros.get("fecha_hasta") or "hoy"}')
    elif _tiene_fecha(fuente):
        # Se dice explícitamente: un análisis que habla de "este mes" sobre
        # todo el historial tiene que notarse en el encabezado.
        partes.append('Periodo: todo el historial')
    if spec.get('comparar_con'):
        desde, hasta = _periodo_comparado(filtros, spec['comparar_con'])
        partes.append(f'Comparado con: {COMPARACIONES[spec["comparar_con"]]} ({desde.isoformat()} a {hasta.isoformat()})')
    if _tiene_estado(fuente):
        lista = _lista(filtros.get('estados'))
        todos = 'todos' if any(c.get('incluye_cancelados') for c in _componentes(fuente)) else 'todos menos cancelado'
        partes.append('Estados: ' + (', '.join(estados.etiqueta(e) for e in lista) if lista else todos))
    for clave, etiqueta in (('producto', 'Producto'), ('categoria', 'Categoría'), ('cliente', 'Cliente'),
                            ('metodo_pago', 'Método de pago'), ('tipo_evento', 'Evento')):
        if filtros.get(clave):
            partes.append(f'{etiqueta}: {filtros[clave]}')
    if filtros.get('solo_stock_bajo'):
        partes.append('Solo stock bajo')
    if filtros.get('solo_agotados'):
        partes.append('Solo agotados')
    if tiendas_por_id:
        nombres = sorted(tiendas_por_id.values())
        partes.append('Tiendas: ' + (', '.join(nombres) if len(nombres) <= 4 else f'{len(nombres)} tiendas'))
    return ' · '.join(partes)
