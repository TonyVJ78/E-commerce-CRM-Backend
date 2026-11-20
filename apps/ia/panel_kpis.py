"""
Panel de KPIs de las tiendas.

No tiene SQL propio: cada KPI y cada serie sale de `informes_consultas.ejecutar`,
el mismo motor del chat de informes, así que el panel y el chat siempre dan las
mismas cifras y respetan las mismas tiendas. Este módulo solo decide qué
consultar, arma el periodo de comparación y da forma a la respuesta.

Ingresos y ganancia se calculan sobre el precio de lista de los ítems (antes de
cupones), como en todo el motor; el ticket promedio y el valor por cliente salen
del total cobrado del pedido.
"""

from datetime import date, timedelta
from typing import NamedTuple

from . import informes_consultas as consultas


MESES_DE_CONTEXTO = 12
MAX_PRODUCTOS = 10
MAX_CATEGORIAS = 12
MAX_CIUDADES = 10
MAX_PRODUCTOS_PARADOS = 5


class Kpi(NamedTuple):
    clave: str
    titulo: str
    fuente: str
    metrica: str
    tipo: str
    mejor_si: str
    descripcion: str


GRUPOS = [
    ('ventas', '¿Cuánto vendí?', [
        Kpi('ingresos', 'Ingresos', 'ventas_productos', 'ingresos', 'moneda', 'sube',
            'Dinero de las ventas del periodo a precio de lista, sin contar pedidos cancelados.'),
        Kpi('pedidos', 'Pedidos', 'pedidos', 'pedidos', 'entero', 'sube',
            'Cantidad de pedidos del periodo, sin contar los cancelados.'),
        Kpi('ticket_promedio', 'Ticket promedio', 'pedidos', 'ticket_promedio', 'moneda', 'sube',
            'Lo que gasta en promedio un cliente por pedido: total cobrado dividido entre los pedidos.'),
        Kpi('unidades', 'Unidades vendidas', 'ventas_productos', 'unidades', 'entero', 'sube',
            'Cantidad de productos que salieron de tu tienda en el periodo.'),
    ]),
    ('ganancia', '¿Cuánto gané?', [
        Kpi('ganancia_bruta', 'Ganancia bruta', 'ventas_productos', 'ganancia_bruta', 'moneda', 'sube',
            'Ingresos menos lo que te costó la mercadería vendida. Solo cuenta ventas con costo cargado.'),
        Kpi('margen_bruto_pct', 'Margen bruto', 'ventas_productos', 'margen_bruto_pct', 'porcentaje', 'sube',
            'De cada 100 Bs que vendes, cuántos quedan como ganancia bruta.'),
        Kpi('gastos_operativos', 'Gastos operativos', 'resultados', 'gastos_operativos', 'moneda', 'baja',
            'Gastos del negocio registrados en el periodo: alquiler, servicios, sueldos, marketing, etc.'),
        Kpi('utilidad_neta', 'Utilidad neta', 'resultados', 'utilidad_neta', 'moneda', 'sube',
            'Lo que realmente te queda: la ganancia bruta menos los gastos operativos.'),
    ]),
    ('clientes', '¿Cómo están mis clientes?', [
        Kpi('clientes_activos', 'Clientes activos', 'clientes', 'clientes', 'entero', 'sube',
            'Clientes distintos que compraron en el periodo.'),
        Kpi('clientes_nuevos', 'Clientes nuevos', 'clientes', 'clientes_nuevos', 'entero', 'sube',
            'Clientes que compraron por primera vez en el periodo.'),
        Kpi('tasa_recompra', 'Tasa de recompra', 'clientes', 'tasa_recompra', 'porcentaje', 'sube',
            'De los clientes activos, qué porcentaje ya te había comprado antes: mide su fidelidad.'),
        Kpi('valor_promedio_cliente', 'Valor por cliente', 'pedidos', 'valor_por_cliente', 'moneda', 'sube',
            'Cuánto compra en promedio cada cliente activo en el periodo.'),
    ]),
    ('operacion', '¿Cómo opera mi tienda?', [
        Kpi('tasa_cancelacion', 'Tasa de cancelación', 'cancelaciones', 'tasa_cancelacion', 'porcentaje', 'baja',
            'Qué porcentaje de los pedidos recibidos se canceló.'),
        Kpi('dias_entrega_promedio', 'Días de entrega', 'entregas', 'dias_entrega_promedio', 'dias', 'baja',
            'Días que pasan en promedio desde que recibes un pedido hasta que se entrega.'),
        Kpi('conversion_vista_compra', 'Conversión de vistas a compras', 'embudo_conversion',
            'tasa_vista_a_compra', 'porcentaje', 'sube',
            'Compras por cada 100 vistas de producto: dice si quien mira termina comprando.'),
        Kpi('dias_de_inventario', 'Días de inventario', 'rotacion_inventario', 'dias_de_inventario', 'dias', 'baja',
            'Cuántos días te dura el stock actual si sigues vendiendo al ritmo del periodo.'),
        Kpi('productos_sin_ventas', 'Productos sin ventas', 'productos_sin_ventas', 'productos', 'entero', 'baja',
            'Productos con stock que no vendieron nada en el periodo: dinero parado en el almacén.'),
    ]),
    ('experiencia', '¿Qué opinan y cómo responden?', [
        Kpi('calificacion_promedio', 'Calificación promedio', 'resenas', 'calificacion_promedio', 'decimal', 'sube',
            'Nota promedio, de 1 a 5, que dan los clientes en sus reseñas del periodo.'),
        Kpi('pct_resenas_positivas', 'Reseñas positivas', 'resenas', 'pct_positivas', 'porcentaje', 'sube',
            'Qué porcentaje de las reseñas del periodo son de 4 o 5 estrellas.'),
        Kpi('tasa_recuperacion_carritos', 'Carritos recuperados', 'carritos_recuperados', 'tasa_recuperacion',
            'porcentaje', 'sube',
            'De los clientes que abandonaron su carrito y recibieron un aviso, qué porcentaje terminó comprando.'),
        Kpi('tasa_uso_cupon', 'Uso de cupones', 'cupones', 'tasa_uso_cupon', 'porcentaje', 'sube',
            'Qué porcentaje de los pedidos usó un cupón de descuento.'),
        Kpi('descuento_promedio', 'Descuento promedio', 'pedidos', 'descuento_promedio', 'moneda', 'baja',
            'Bs que se descuentan en promedio a cada pedido que usó un cupón.'),
    ]),
]

# Métricas que el panel necesita aunque no sean un KPI (las notas y el embudo).
EXTRAS = {
    'ventas_productos': ['ventas_sin_costo_pct'],
    'embudo_conversion': ['vistas', 'carritos', 'compras'],
}


def _consultar(tienda_ids, fuente, metricas, desde, hasta, agrupar=(), comparar_con=None, **spec):
    """Una consulta del motor del chat, devuelta como lista de `{columna: valor}`."""
    consulta = consultas.normalizar({
        'fuente': fuente, 'agrupar_por': list(agrupar), 'metricas': metricas,
        'filtros': {'fecha_desde': desde.isoformat(), 'fecha_hasta': hasta.isoformat()}, **spec,
    })
    # Se asigna aquí y no en `normalizar`: ese tope de 3 métricas al comparar es para el
    # modelo del chat y el panel pide hasta 6 de una fuente en una sola consulta.
    consulta['comparar_con'] = comparar_con
    resultado = consultas.ejecutar(consulta, tienda_ids)
    claves = [c['clave'] for c in resultado['columnas']]
    return [dict(zip(claves, fila)) for fila in resultado['filas']]


def _kpis_por_fuente():
    metricas = {fuente: list(extras) for fuente, extras in EXTRAS.items()}
    for _, _, kpis in GRUPOS:
        for kpi in kpis:
            if kpi.metrica not in metricas.setdefault(kpi.fuente, []):
                metricas[kpi.fuente].append(kpi.metrica)
    return metricas


def _meses_hasta(hasta, cantidad):
    anio, mes = hasta.year, hasta.month
    meses = []
    for _ in range(cantidad):
        meses.append(f'{anio:04d}-{mes:02d}')
        anio, mes = (anio - 1, 12) if mes == 1 else (anio, mes - 1)
    return meses[::-1]


def _serie_diaria(filas, desde, hasta):
    por_dia = {fila['dia']: fila for fila in filas}
    serie = []
    for indice in range((hasta - desde).days + 1):
        dia = (desde + timedelta(days=indice)).isoformat()
        fila = por_dia.get(dia, {})
        serie.append({'fecha': dia, 'ingresos': fila.get('ingresos', 0), 'pedidos': fila.get('pedidos', 0)})
    return serie


def _resultado_mensual(tienda_ids, hasta):
    meses = _meses_hasta(hasta, MESES_DE_CONTEXTO)
    desde = date(int(meses[0][:4]), int(meses[0][5:]), 1)
    filas = _consultar(tienda_ids, 'resultados', ['ingresos', 'ganancia_bruta', 'gastos_operativos', 'utilidad_neta'],
                       desde, hasta, agrupar=['mes'])
    por_mes = {fila['mes']: fila for fila in filas}
    vacio = {'ingresos': 0, 'ganancia_bruta': 0, 'gastos_operativos': 0, 'utilidad_neta': 0}
    return [{
        'mes': mes,
        'ingresos': por_mes.get(mes, vacio)['ingresos'],
        'ganancia_bruta': por_mes.get(mes, vacio)['ganancia_bruta'],
        'gastos': por_mes.get(mes, vacio)['gastos_operativos'],
        'utilidad_neta': por_mes.get(mes, vacio)['utilidad_neta'],
    } for mes in meses]


def _notas(valores, comparar_con, hay_tiendas):
    notas = []
    if not hay_tiendas:
        notas.append('No tienes tiendas asignadas: el panel no tiene datos que mostrar.')
    sin_costo = valores[('ventas_productos', 'ventas_sin_costo_pct')][0]
    if sin_costo is not None and sin_costo >= 100:
        notas.append('Ninguna venta del periodo tiene costo cargado: la ganancia y el margen no se pueden calcular.')
    elif sin_costo:
        notas.append(
            f'El {sin_costo:.1f} % de las ventas del periodo no tiene costo cargado: la ganancia bruta, el margen '
            'y la utilidad neta cubren solo el resto.')
    if valores[('pedidos', 'descuento_promedio')][0]:
        notas.append('Los ingresos y la ganancia se calculan a precio de lista, antes de los cupones; '
                     'el ticket promedio y el valor por cliente son lo realmente cobrado.')
    if comparar_con:
        notas.append('Los días de inventario y los productos sin ventas usan el stock de hoy, también al comparar '
                     'con el periodo anterior.')
    return notas


def calcular(tiendas, tienda_id, desde, hasta, comparar_con):
    """Arma el panel. `tiendas` son las permitidas (`[{'id', 'nombre'}]`); `comparar_con` puede ser `'ninguno'`."""
    comparar = comparar_con if comparar_con in consultas.COMPARACIONES else None
    tienda_ids = [tienda_id] if tienda_id else [t['id'] for t in tiendas]

    valores = {}
    for fuente, metricas in _kpis_por_fuente().items():
        fila = _consultar(tienda_ids, fuente, metricas, desde, hasta, comparar_con=comparar)[0]
        for metrica in metricas:
            valores[(fuente, metrica)] = (
                fila[metrica], fila.get(f'{metrica}_anterior'), fila.get(f'{metrica}_variacion'))

    grupos = [{
        'clave': clave, 'titulo': titulo,
        'kpis': [{
            'clave': kpi.clave, 'titulo': kpi.titulo,
            'valor': valores[(kpi.fuente, kpi.metrica)][0],
            'anterior': valores[(kpi.fuente, kpi.metrica)][1],
            'variacion': valores[(kpi.fuente, kpi.metrica)][2],
            'tipo': kpi.tipo, 'mejor_si': kpi.mejor_si, 'descripcion': kpi.descripcion,
        } for kpi in kpis],
    } for clave, titulo, kpis in GRUPOS]

    comparado = consultas._periodo_comparado(
        {'fecha_desde': desde.isoformat(), 'fecha_hasta': hasta.isoformat()}, comparar) if comparar else None

    dias = _consultar(tienda_ids, 'ventas_productos', ['ingresos', 'pedidos'], desde, hasta, agrupar=['dia'])
    productos = _consultar(tienda_ids, 'ventas_productos', ['ingresos', 'unidades', 'margen_bruto_pct'], desde, hasta,
                           agrupar=['producto'], ordenar_por='ingresos', limite=MAX_PRODUCTOS)
    categorias = _consultar(tienda_ids, 'ventas_productos', ['ingresos', 'participacion_ingresos'], desde, hasta,
                            agrupar=['categoria'], ordenar_por='ingresos', limite=MAX_CATEGORIAS)
    franjas = _consultar(tienda_ids, 'pedidos', ['pedidos'], desde, hasta, agrupar=['dia_semana', 'hora'])
    ciudades = _consultar(tienda_ids, 'ventas_productos', ['pedidos', 'ingresos'], desde, hasta,
                          agrupar=['ciudad'], ordenar_por='ingresos', limite=MAX_CIUDADES)

    return {
        'periodo': {
            'desde': desde.isoformat(), 'hasta': hasta.isoformat(),
            'comparado_desde': comparado[0].isoformat() if comparado else None,
            'comparado_hasta': comparado[1].isoformat() if comparado else None,
        },
        'tiendas': tiendas,
        'tienda_id': tienda_id,
        'grupos': grupos,
        'series': {
            'ventas_diarias': _serie_diaria(dias, desde, hasta),
            'resultado_mensual': _resultado_mensual(tienda_ids, hasta),
            'top_productos': [{
                'producto': fila['producto'], 'ingresos': fila['ingresos'], 'unidades': fila['unidades'],
                'margen_pct': fila['margen_bruto_pct'],
            } for fila in productos],
            'ventas_por_categoria': [{
                'categoria': fila['categoria'], 'ingresos': fila['ingresos'],
                'participacion_pct': fila['participacion_ingresos'],
            } for fila in categorias],
            'embudo': {metrica: valores[('embudo_conversion', metrica)][0]
                       for metrica in ('vistas', 'carritos', 'compras')},
            'pedidos_por_dia_hora': sorted(
                ({'dia_semana': fila['dia_semana'], 'hora': fila['hora'], 'pedidos': fila['pedidos']}
                 for fila in franjas),
                key=lambda fila: (fila['dia_semana'], fila['hora'])),
            'ventas_por_ciudad': [{
                'ciudad': fila['ciudad'], 'pedidos': fila['pedidos'], 'ingresos': fila['ingresos'],
            } for fila in ciudades],
        },
        'notas': _notas(valores, comparar, bool(tiendas)),
    }


def datos_adicionales(panel):
    """Cifras que el panel no muestra pero ayudan a interpretarlo, en el mismo alcance y periodo."""
    tienda_ids = [panel['tienda_id']] if panel['tienda_id'] else [t['id'] for t in panel['tiendas']]
    desde, hasta = date.fromisoformat(panel['periodo']['desde']), date.fromisoformat(panel['periodo']['hasta'])
    concentracion = _consultar(tienda_ids, 'ventas_productos', ['concentracion_top20'], desde, hasta,
                               agrupar=['producto'], limite=1)
    margen = _consultar(tienda_ids, 'ventas_productos', ['ingresos', 'margen_bruto_pct'], desde, hasta,
                        agrupar=['categoria'], ordenar_por='ingresos', limite=MAX_CATEGORIAS)
    parados = _consultar(tienda_ids, 'productos_sin_ventas', ['unidades_paradas', 'valor_parado'], desde, hasta,
                         agrupar=['producto'], ordenar_por='valor_parado', limite=MAX_PRODUCTOS_PARADOS)
    return {
        'pct_ingresos_del_20pct_de_productos_que_mas_venden': concentracion[0]['concentracion_top20']
        if concentracion else None,
        'margen_por_categoria': margen,
        'productos_sin_ventas_de_mayor_valor': parados,
    }
