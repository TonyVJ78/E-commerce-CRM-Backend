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
"""

from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import (
    Avg, Count, DecimalField, ExpressionWrapper, F, Max, Min, Q, Sum,
)
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek
from django.utils import timezone

from apps.catalogo.models import Variante
from apps.pedidos import estados
from apps.pedidos.models import ItemPedido, Pago, Pedido, Resena
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
# con dos productos cuenta en las dos filas) y los promedios no se totalizan.
TEXTO, ENTERO, MONEDA, DECIMAL, FECHA = 'texto', 'entero', 'moneda', 'decimal', 'fecha'


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

def _dim(etiqueta, campos, mostrar=None, tipo=TEXTO):
    campos = campos if isinstance(campos, (list, tuple)) else [campos]
    return {'etiqueta': etiqueta, 'campos': list(campos), 'mostrar': mostrar or campos[-1], 'tipo': tipo}


def _tiempo(etiqueta, trunc):
    return {'etiqueta': etiqueta, 'trunc': trunc, 'tipo': FECHA}


_INGRESOS_ITEM = ExpressionWrapper(
    F('cantidad') * F('precio_unitario'), output_field=DecimalField(max_digits=14, decimal_places=2))
_VALOR_STOCK = ExpressionWrapper(
    F('stock') * F('precio'), output_field=DecimalField(max_digits=16, decimal_places=2))

ESTADOS_PEDIDO = estados.ESTADOS


FUENTES = {
    'ventas_productos': {
        'descripcion': (
            'Líneas vendidas (ítems de pedidos). Para qué productos, variantes o categorías '
            'se venden más, unidades e ingresos por producto. Excluye pedidos cancelados '
            'salvo que se filtre por estado.'
        ),
        'modelo': ItemPedido,
        'tienda': 'tienda',
        'fecha': 'pedido__fecha',
        'estado': 'pedido__estado_actual',
        'dimensiones': {
            'tienda': _dim('Tienda', ['tienda_id', 'tienda__nombre']),
            'producto': _dim('Producto', ['variante__producto_id', 'variante__producto__nombre']),
            'variante': _dim('Variante', ['variante_id', 'variante__producto__nombre', 'variante__nombre'],
                             mostrar='__variante__'),
            'categoria': _dim('Categoría', ['variante__producto__categoria__nombre']),
            'estado': _dim('Estado', ['pedido__estado_actual']),
            'dia': _tiempo('Día', TruncDay),
            'semana': _tiempo('Semana', TruncWeek),
            'mes': _tiempo('Mes', TruncMonth),
        },
        'metricas': {
            'unidades': ('Unidades vendidas', ENTERO, lambda: Sum('cantidad'), True),
            'ingresos': ('Ingresos (Bs)', MONEDA, lambda: Sum(_INGRESOS_ITEM), True),
            'pedidos': ('Pedidos', ENTERO, lambda: Count('pedido', distinct=True), False),
            'precio_promedio': ('Precio unitario promedio (Bs)', MONEDA, lambda: Avg('precio_unitario'), False),
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
            'tienda': _dim('Tienda', ['tienda_id', 'tienda__nombre']),
            'estado': _dim('Estado', ['estado_actual']),
            'cliente': _dim('Cliente', ['cliente_id', 'cliente__email']),
            'dia': _tiempo('Día', TruncDay),
            'semana': _tiempo('Semana', TruncWeek),
            'mes': _tiempo('Mes', TruncMonth),
        },
        'metricas': {
            'pedidos': ('Pedidos', ENTERO, lambda: Count('id'), True),
            'monto_total': ('Monto total (Bs)', MONEDA, lambda: Sum('total'), True),
            'ticket_promedio': ('Ticket promedio (Bs)', MONEDA, lambda: Avg('total'), False),
            'clientes': ('Clientes distintos', ENTERO, lambda: Count('cliente', distinct=True), False),
            'primera_compra': ('Primera compra', FECHA, lambda: Min('fecha'), False),
            'ultima_compra': ('Última compra', FECHA, lambda: Max('fecha'), False),
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
        'base': lambda qs: qs.filter(producto__activo=True, activa=True),
        'dimensiones': {
            'tienda': _dim('Tienda', ['producto__tienda_id', 'producto__tienda__nombre']),
            'producto': _dim('Producto', ['producto_id', 'producto__nombre']),
            'variante': _dim('Variante', ['id', 'producto__nombre', 'nombre'], mostrar='__variante__'),
            'categoria': _dim('Categoría', ['producto__categoria__nombre']),
            'sku': _dim('SKU', ['sku']),
        },
        'metricas': {
            'stock': ('Stock', ENTERO, lambda: Sum('stock'), True),
            'stock_minimo': ('Stock mínimo', ENTERO, lambda: Sum('stock_minimo'), True),
            'valor_inventario': ('Valor del inventario (Bs)', MONEDA, lambda: Sum(_VALOR_STOCK), True),
            'precio': ('Precio (Bs)', MONEDA, lambda: Avg('precio'), False),
            'variantes': ('Variantes', ENTERO, lambda: Count('id'), True),
            'productos': ('Productos', ENTERO, lambda: Count('producto', distinct=True), False),
        },
        'texto': {'producto': 'producto__nombre', 'categoria': 'producto__categoria__nombre'},
    },
    'resenas': {
        'descripcion': 'Reseñas de clientes. Para calificación promedio y cantidad de reseñas por producto o tienda.',
        'modelo': Resena,
        'tienda': 'tienda',
        'fecha': 'fecha',
        'estado': None,
        'dimensiones': {
            'tienda': _dim('Tienda', ['tienda_id', 'tienda__nombre']),
            'producto': _dim('Producto', ['producto_id', 'producto__nombre']),
            'calificacion': _dim('Calificación', ['calificacion'], tipo=ENTERO),
            'mes': _tiempo('Mes', TruncMonth),
        },
        'metricas': {
            'resenas': ('Reseñas', ENTERO, lambda: Count('id'), True),
            'calificacion_promedio': ('Calificación promedio', DECIMAL, lambda: Avg('calificacion'), False),
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
            'tienda': _dim('Tienda', ['tienda_id', 'tienda__nombre']),
            'metodo_pago': _dim('Método de pago', ['metodo_pago__nombre']),
            'estado_pago': _dim('Estado del pago', ['estado']),
            'dia': _tiempo('Día', TruncDay),
            'mes': _tiempo('Mes', TruncMonth),
        },
        'metricas': {
            'pagos': ('Pagos', ENTERO, lambda: Count('id'), True),
            'monto': ('Monto (Bs)', MONEDA, lambda: Sum('monto'), True),
        },
        'texto': {},
    },
    'actividad': {
        'descripcion': (
            'Actividad de los clientes en la tienda: vistas y clics en productos, búsquedas y '
            'agregados al carrito. Para productos más vistos, términos más buscados o '
            'conversión de interés a carrito.'
        ),
        'modelo': EventoUsuario,
        'tienda': 'tienda',
        'fecha': 'fecha',
        'estado': None,
        'dimensiones': {
            'tienda': _dim('Tienda', ['tienda_id', 'tienda__nombre']),
            'producto': _dim('Producto', ['producto_id', 'producto__nombre']),
            'tipo_evento': _dim('Tipo de evento', ['tipo_evento']),
            'termino_busqueda': _dim('Término buscado', ['termino_busqueda']),
            'dia': _tiempo('Día', TruncDay),
            'mes': _tiempo('Mes', TruncMonth),
        },
        'metricas': {
            'eventos': ('Eventos', ENTERO, lambda: Count('id'), True),
            'clientes': ('Clientes distintos', ENTERO, lambda: Count('cliente', distinct=True), False),
        },
        'texto': {'producto': 'producto__nombre'},
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


def catalogo_para_modelo():
    """Descripción compacta de las fuentes, para el prompt del sistema."""
    lineas = []
    for clave, fuente in FUENTES.items():
        lineas.append(f'- `{clave}`: {fuente["descripcion"]}')
        lineas.append(f'  - agrupar_por: {", ".join(fuente["dimensiones"])}')
        lineas.append(f'  - metricas: {", ".join(fuente["metricas"])}')
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
        'ordenar_por': {
            'type': 'string',
            'description': 'Una métrica o columna de agrupar_por. Por defecto la primera métrica (o el tiempo si se agrupa por fecha).',
        },
        'descendente': {'type': 'boolean', 'description': 'Orden descendente. Por defecto true para métricas.'},
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


def normalizar(spec):
    """Valida la especificación y la devuelve completa con sus valores por defecto."""
    if not isinstance(spec, dict):
        raise ConsultaInvalida('La consulta debe ser un objeto.')
    fuente_clave = spec.get('fuente')
    if fuente_clave not in FUENTES:
        raise ConsultaInvalida(f'Fuente desconocida. Usa una de: {", ".join(FUENTES)}.')
    fuente = FUENTES[fuente_clave]

    agrupar = []
    for dim in _lista(spec.get('agrupar_por')):
        if dim not in fuente['dimensiones']:
            raise ConsultaInvalida(
                f'`{dim}` no se puede agrupar en {fuente_clave}. Opciones: {", ".join(fuente["dimensiones"])}.')
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
    if fuente['fecha'] is None and (filtros.get('fecha_desde') or filtros.get('fecha_hasta')):
        raise ConsultaInvalida(f'La fuente {fuente_clave} no tiene fechas; quita el filtro de fecha.')
    for estado in _lista(filtros.get('estados')):
        if estado not in ESTADOS_PEDIDO and estado != estados.COMPLETADO_LEGADO:
            raise ConsultaInvalida(f'Estado desconocido: {estado}.')

    ordenar_por = spec.get('ordenar_por') or None
    if ordenar_por and ordenar_por not in agrupar and ordenar_por not in metricas:
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
        'ordenar_por': ordenar_por,
        'descendente': spec.get('descendente'),
        'limite': max(1, min(limite, MAX_FILAS)),
    }


def _aplicar_filtros(qs, fuente, filtros, tienda_ids):
    qs = qs.filter(**{f'{fuente["tienda"]}__in': tienda_ids})

    if fuente['fecha']:
        if filtros.get('fecha_desde'):
            desde = _fecha(filtros['fecha_desde'], 'fecha_desde')
            qs = qs.filter(**{f'{fuente["fecha"]}__gte': _inicio_del_dia(desde)})
        if filtros.get('fecha_hasta'):
            hasta = _fecha(filtros['fecha_hasta'], 'fecha_hasta')
            qs = qs.filter(**{f'{fuente["fecha"]}__lt': _inicio_del_dia(hasta + timedelta(days=1))})

    if fuente['estado']:
        pedidos = _lista(filtros.get('estados'))
        if pedidos:
            # `completado` es el nombre viejo de `pendiente` (CU-22).
            if estados.PENDIENTE in pedidos:
                pedidos.append(estados.COMPLETADO_LEGADO)
            qs = qs.filter(**{f'{fuente["estado"]}__in': pedidos})
        else:
            qs = qs.exclude(**{fuente['estado']: estados.CANCELADO})

    for filtro, campo in fuente.get('texto', {}).items():
        valor = str(filtros.get(filtro) or '').strip()
        if valor:
            qs = qs.filter(**{f'{campo}__icontains': valor})

    if fuente['modelo'] is Variante:
        if filtros.get('solo_stock_bajo'):
            qs = qs.filter(stock__lte=F('stock_minimo'))
        if filtros.get('solo_agotados'):
            qs = qs.filter(stock=0)
    if fuente['modelo'] is EventoUsuario and filtros.get('tipo_evento'):
        qs = qs.filter(tipo_evento=filtros['tipo_evento'])
    if fuente['modelo'] is Pago and filtros.get('metodo_pago'):
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
            return valor.date().isoformat() if dim in ('dia', 'semana') else valor.strftime('%Y-%m-%d %H:%M')
        return valor.isoformat()
    if tipo == ENTERO:
        return int(valor)
    if tipo in (MONEDA, DECIMAL):
        return float(Decimal(valor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    if dim == 'estado':
        return estados.etiqueta(valor)
    return str(valor)


def ejecutar(spec, tienda_ids):
    """Corre una especificación ya normalizada sobre las tiendas indicadas.

    Devuelve `{columnas, filas, total_filas, truncado}`; `filas` es una lista
    de listas en el orden de `columnas`.
    """
    fuente = FUENTES[spec['fuente']]
    qs = fuente['modelo'].objects.all()
    if 'base' in fuente:
        qs = fuente['base'](qs)
    qs = _aplicar_filtros(qs, fuente, spec['filtros'], list(tienda_ids))

    valores, anotaciones_tiempo, columnas = [], {}, []
    for dim in spec['agrupar_por']:
        definicion = fuente['dimensiones'][dim]
        if 'trunc' in definicion:
            alias = f'_t_{dim}'
            anotaciones_tiempo[alias] = definicion['trunc'](fuente['fecha'])
            valores.append(alias)
        else:
            valores.extend(c for c in definicion['campos'] if c not in valores)
        columnas.append({'clave': dim, 'titulo': definicion['etiqueta'], 'tipo': definicion['tipo'], 'sumable': False})

    agregados = {}
    for met in spec['metricas']:
        titulo, tipo, expresion, sumable = fuente['metricas'][met]
        agregados[f'_m_{met}'] = expresion()
        columnas.append({'clave': met, 'titulo': titulo, 'tipo': tipo, 'sumable': sumable})

    if anotaciones_tiempo:
        qs = qs.annotate(**anotaciones_tiempo)
    if valores:
        qs = qs.values(*valores).annotate(**agregados)
    else:
        qs = [qs.aggregate(**agregados)]

    def _orden_campo(clave):
        if clave in spec['metricas']:
            return f'_m_{clave}'
        definicion = fuente['dimensiones'][clave]
        return f'_t_{clave}' if 'trunc' in definicion else definicion['mostrar'].replace('__variante__', definicion['campos'][1])

    if valores:
        tiempo = next((d for d in spec['agrupar_por'] if 'trunc' in fuente['dimensiones'][d]), None)
        clave_orden = spec['ordenar_por'] or (tiempo or spec['metricas'][0])
        descendente = spec['descendente']
        if descendente is None:
            descendente = clave_orden in spec['metricas']
        campo = _orden_campo(clave_orden)
        orden = F(campo).desc(nulls_last=True) if descendente else F(campo).asc(nulls_last=True)
        # El segundo criterio deja el orden estable entre ejecuciones.
        qs = qs.order_by(orden, *valores)

    total_filas = qs.count() if valores else 1
    registros = list(qs[:spec['limite']]) if valores else qs

    filas = []
    for registro in registros:
        fila = []
        for dim in spec['agrupar_por']:
            definicion = fuente['dimensiones'][dim]
            if 'trunc' in definicion:
                fila.append(_valor(registro[f'_t_{dim}'], FECHA, dim))
            elif definicion['mostrar'] == '__variante__':
                producto, variante = registro[definicion['campos'][1]], registro[definicion['campos'][2]]
                fila.append(f'{producto} — {variante}' if variante else str(producto))
            else:
                valor = registro[definicion['mostrar']]
                fila.append(_valor(valor, definicion['tipo'], dim) if valor is not None else '(sin dato)')
        for met in spec['metricas']:
            tipo = fuente['metricas'][met][1]
            valor = registro[f'_m_{met}']
            fila.append(_valor(valor, tipo) if valor is not None else (0 if tipo in (ENTERO, MONEDA) else None))
        filas.append(fila)

    return {
        'columnas': columnas,
        'filas': filas,
        'total_filas': total_filas,
        'truncado': total_filas > len(filas),
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
    partes = []
    if filtros.get('fecha_desde') or filtros.get('fecha_hasta'):
        partes.append(f'Periodo: {filtros.get("fecha_desde") or "inicio"} a {filtros.get("fecha_hasta") or "hoy"}')
    elif FUENTES[spec['fuente']]['fecha']:
        # Se dice explícitamente: un análisis que habla de "este mes" sobre
        # todo el historial tiene que notarse en el encabezado.
        partes.append('Periodo: todo el historial')
    if FUENTES[spec['fuente']]['estado']:
        lista = _lista(filtros.get('estados'))
        partes.append('Estados: ' + (', '.join(estados.etiqueta(e) for e in lista) if lista else 'todos menos cancelado'))
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
