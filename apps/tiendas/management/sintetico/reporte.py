"""Reporte Markdown de lo sembrado: conteos reales de la base y consultas SQL para comprobarlos."""

from decimal import Decimal

from django.db.models import Avg, Count, DecimalField, F, Max, Min, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.catalogo.models import Categoria, Producto, Variante, VarianteStockMovimiento
from apps.crm.models import (
    CampanaCarrito, FichaCliente, RegistroRecuperacionCarrito, ReglaSegmentacion, Segmento, SegmentoCliente,
)
from apps.finanzas.models import GastoOperativo
from apps.ia.models import EventoUsuario
from apps.marketing.models import Campana, Cupon, CuponUso
from apps.pedidos import estados
from apps.pedidos.models import (
    Carrito, DireccionEnvio, Envio, HistorialEstadoPedido, ItemCarrito, ItemPedido, Pago, Pedido, Resena,
)
from apps.tiendas.models import DireccionTienda

from . import persistencia
from .simulacion import ZONA

CON_TIENDA = [
    DireccionTienda, FichaCliente, Segmento, SegmentoCliente, ReglaSegmentacion, Categoria, Producto,
    DireccionEnvio, Carrito, ItemCarrito, CampanaCarrito, Campana, Cupon, CuponUso, Pedido, ItemPedido,
    HistorialEstadoPedido, Pago, Envio, Resena, EventoUsuario, GastoOperativo,
]

COSTO_ITEM = Sum(F('cantidad') * F('costo_unitario'), output_field=DecimalField())


def bs(valor):
    return f'{(valor or Decimal("0")):,.2f}'


def conteos_por_tabla(tienda, empresa):
    """Cada fila: (tabla, cantidad, fragmento SQL `FROM ... WHERE ...` que la cuenta)."""
    t = tienda.id
    prefijo, dominio = persistencia.prefijo_y_dominio(empresa)
    filas = [
        ('usuario (clientes sintéticos)', persistencia.clientes_sinteticos(empresa).count(),
         f"usuario WHERE email LIKE '{prefijo}%{dominio}'"),
        ('tienda', 1, f'tienda WHERE id = {t}'),
        ('variante', Variante.objects.filter(producto__tienda=tienda).count(),
         f'variante v JOIN producto p ON p.id = v.producto_id WHERE p.tienda_id = {t}'),
        ('variante_stock_movimiento', VarianteStockMovimiento.objects.filter(variante__producto__tienda=tienda).count(),
         'variante_stock_movimiento m JOIN variante v ON v.id = m.variante_id '
         f'JOIN producto p ON p.id = v.producto_id WHERE p.tienda_id = {t}'),
        ('registro_recuperacion_carrito', RegistroRecuperacionCarrito.objects.filter(campana__tienda=tienda).count(),
         'registro_recuperacion_carrito r JOIN campana_carrito c ON c.id = r.campana_id '
         f'WHERE c.tienda_id = {t}'),
    ]
    filas += [
        (modelo._meta.db_table, modelo.objects.filter(tienda=tienda).count(),
         f'{modelo._meta.db_table} WHERE tienda_id = {t}')
        for modelo in CON_TIENDA
    ]
    return sorted(filas, key=lambda fila: fila[0])


def resultado_mensual(tienda):
    pedidos = Pedido.objects.filter(tienda=tienda).exclude(estado_actual=estados.CANCELADO)
    ingresos = {
        (f['mes'].year, f['mes'].month): f
        for f in pedidos.annotate(mes=TruncMonth('fecha', tzinfo=ZONA)).values('mes')
        .annotate(n=Count('id'), ingresos=Sum('total'))
    }
    costos = {
        (f['mes'].year, f['mes'].month): f['costo']
        for f in ItemPedido.objects.filter(pedido__in=pedidos)
        .annotate(mes=TruncMonth('pedido__fecha', tzinfo=ZONA)).values('mes').annotate(costo=COSTO_ITEM)
    }
    gastos = {
        (f['mes'].year, f['mes'].month): f['gastos']
        for f in GastoOperativo.objects.filter(tienda=tienda)
        .annotate(mes=TruncMonth('fecha')).values('mes').annotate(gastos=Sum('monto'))
    }
    filas = []
    for mes in sorted(ingresos):
        ingreso = ingresos[mes]['ingresos']
        bruta = ingreso - costos.get(mes, Decimal('0'))
        gasto = gastos.get(mes, Decimal('0'))
        filas.append((mes, ingresos[mes]['n'], ingreso, bruta, gasto, bruta - gasto))
    return filas


def construir(tienda, empresa, opciones, duracion):
    t = tienda.id
    conteos = conteos_por_tabla(tienda, empresa)
    pedidos = Pedido.objects.filter(tienda=tienda)
    vigentes = pedidos.exclude(estado_actual=estados.CANCELADO)
    ingresos = vigentes.aggregate(s=Sum('total'))['s'] or Decimal('0')
    costo = ItemPedido.objects.filter(pedido__in=vigentes).aggregate(s=COSTO_ITEM)['s'] or Decimal('0')
    gastos = GastoOperativo.objects.filter(tienda=tienda).aggregate(s=Sum('monto'))['s'] or Decimal('0')
    rango_pedidos = pedidos.aggregate(a=Min('fecha'), b=Max('fecha'))
    rango_eventos = EventoUsuario.objects.filter(tienda=tienda).aggregate(a=Min('fecha'), b=Max('fecha'))
    rango_resenas = Resena.objects.filter(tienda=tienda).aggregate(a=Min('fecha'), b=Max('fecha'))
    por_estado = pedidos.values('estado_actual').annotate(n=Count('id')).order_by('-n')
    por_estrella = {f['calificacion']: f['n'] for f in
                    Resena.objects.filter(tienda=tienda).values('calificacion').annotate(n=Count('id'))}
    peores = list(
        Resena.objects.filter(tienda=tienda, producto__isnull=False).values('producto__nombre')
        .annotate(promedio=Avg('calificacion'), n=Count('id')).filter(n__gte=5).order_by('promedio')[:3]
    )
    por_evento = {f['tipo_evento']: f['n'] for f in
                  EventoUsuario.objects.filter(tienda=tienda).values('tipo_evento').annotate(n=Count('id'))}
    con_tipo_cambio = pedidos.exclude(tipo_cambio_usd__isnull=True).count()
    usos_cupon = CuponUso.objects.filter(tienda=tienda).count()
    recuperados = RegistroRecuperacionCarrito.objects.filter(campana__tienda=tienda, recuperado=True).count()
    notificados = RegistroRecuperacionCarrito.objects.filter(campana__tienda=tienda).count()

    def fecha(momento):
        return timezone.localtime(momento).strftime('%Y-%m-%d %H:%M') if momento else '-'

    lineas = [
        '# Siembra de datos sintéticos de Kantu Market',
        '',
        f'- Ejecutado: {timezone.localtime().strftime("%Y-%m-%d %H:%M")} (duración {duracion:.1f} s)',
        f'- Empresa propietaria: `{empresa.email}` (usuario id {empresa.id})',
        f'- Tienda dedicada: **{tienda.nombre}** (tienda_id = {t}, slug `{tienda.slug}`)',
        f'- Semilla: `{opciones["semilla"]}` (misma semilla, parámetros y fecha de corte producen los mismos datos)',
        f'- Parámetros: meses={opciones["meses"]}, clientes={opciones["clientes"]}, pedidos={opciones["pedidos"]}, '
        f'hasta={opciones["hasta"]}',
        '',
        '## Filas creadas por tabla',
        '',
        '| Tabla | Filas |',
        '|---|---:|',
        *[f'| {tabla} | {cantidad:,} |' for tabla, cantidad, _ in conteos],
        f'| **Total** | **{sum(c for _, c, _ in conteos):,}** |',
        '',
        '## Rango de fechas',
        '',
        '| Dato | Primera | Última |',
        '|---|---|---|',
        f'| Pedidos | {fecha(rango_pedidos["a"])} | {fecha(rango_pedidos["b"])} |',
        f'| Eventos de usuario | {fecha(rango_eventos["a"])} | {fecha(rango_eventos["b"])} |',
        f'| Reseñas | {fecha(rango_resenas["a"])} | {fecha(rango_resenas["b"])} |',
        '',
        '## Totales de control (pedidos no cancelados)',
        '',
        '| Concepto | Valor |',
        '|---|---:|',
        f'| Ingresos (Bs) | {bs(ingresos)} |',
        f'| Costo de lo vendido (Bs) | {bs(costo)} |',
        f'| Utilidad bruta (Bs) | {bs(ingresos - costo)} |',
        f'| Margen bruto | {(ingresos - costo) * 100 / ingresos:.1f} % |' if ingresos else '| Margen bruto | - |',
        f'| Gastos operativos (Bs) | {bs(gastos)} |',
        f'| Utilidad neta (Bs) | {bs(ingresos - costo - gastos)} |',
        f'| Ticket promedio (Bs) | {bs(ingresos / vigentes.count()) if vigentes.count() else "-"} |',
        f'| Pedidos con tipo de cambio guardado | {con_tipo_cambio:,} |',
        f'| Usos de cupón | {usos_cupon:,} |',
        f'| Carritos notificados / recuperados | {notificados:,} / {recuperados:,} |',
        '',
        '## Pedidos por estado',
        '',
        '| Estado | Pedidos | % |',
        '|---|---:|---:|',
        *[f'| {f["estado_actual"]} | {f["n"]:,} | {f["n"] * 100 / pedidos.count():.1f} % |' for f in por_estado],
        '',
        '## Reseñas por estrella',
        '',
        '| Estrellas | Reseñas |',
        '|---:|---:|',
        *[f'| {n} | {por_estrella.get(n, 0):,} |' for n in range(5, 0, -1)],
        '',
        '## Productos peor calificados (al menos 5 reseñas)',
        '',
        '| Producto | Promedio | Reseñas |',
        '|---|---:|---:|',
        *[f'| {f["producto__nombre"]} | {f["promedio"]:.2f} | {f["n"]} |' for f in peores],
        '',
        '## Embudo de eventos',
        '',
        '| Evento | Filas |',
        '|---|---:|',
        *[f'| {tipo} | {por_evento.get(tipo, 0):,} |' for tipo in ('VIEW', 'CLICK', 'SEARCH', 'CART')],
        f'| Pedidos (compra) | {pedidos.count():,} |',
        '',
        '## Resultado mensual (Bs, pedidos no cancelados)',
        '',
        '| Mes | Pedidos | Ingresos | Utilidad bruta | Gastos | Utilidad neta |',
        '|---|---:|---:|---:|---:|---:|',
        *[f'| {a}-{m:02d} | {n:,} | {bs(i)} | {bs(b)} | {bs(g)} | {bs(neto)} |'
          for (a, m), n, i, b, g, neto in resultado_mensual(tienda)],
        '',
        '## Consultas SQL de verificación (psql)',
        '',
        'Cada consulta debe devolver el mismo número que la tabla de arriba.',
        '',
        '```sql',
        '-- Filas por tabla',
        *[f'SELECT COUNT(*) AS {tabla.split(" ")[0]} FROM {sql};' for tabla, _, sql in conteos],
        '',
        '-- Totales de control',
        f"SELECT SUM(total) AS ingresos FROM pedido WHERE tienda_id = {t} AND estado_actual <> 'cancelado';",
        'SELECT SUM(ip.cantidad * ip.costo_unitario) AS costo FROM item_pedido ip '
        f"JOIN pedido p ON p.id = ip.pedido_id WHERE p.tienda_id = {t} AND p.estado_actual <> 'cancelado';",
        f'SELECT SUM(monto) AS gastos FROM gasto_operativo WHERE tienda_id = {t};',
        f'SELECT estado_actual, COUNT(*) FROM pedido WHERE tienda_id = {t} GROUP BY 1 ORDER BY 2 DESC;',
        f'SELECT calificacion, COUNT(*) FROM resena WHERE tienda_id = {t} GROUP BY 1 ORDER BY 1 DESC;',
        'SELECT p.nombre, ROUND(AVG(r.calificacion), 2), COUNT(*) FROM resena r JOIN producto p ON p.id = r.producto_id '
        f'WHERE r.tienda_id = {t} GROUP BY 1 HAVING COUNT(*) >= 5 ORDER BY 2 LIMIT 3;',
        f'SELECT tipo_evento, COUNT(*) FROM evento_usuario WHERE tienda_id = {t} GROUP BY 1;',
        f'SELECT MIN(fecha), MAX(fecha) FROM pedido WHERE tienda_id = {t};',
        '',
        '-- Resultado mensual',
        "SELECT date_trunc('month', fecha AT TIME ZONE 'America/La_Paz')::date AS mes, COUNT(*) AS pedidos, "
        f"SUM(total) AS ingresos FROM pedido WHERE tienda_id = {t} AND estado_actual <> 'cancelado' GROUP BY 1 ORDER BY 1;",
        '',
        '-- Coherencia: el total de cada pedido sin cupón es la suma de sus ítems (debe dar 0 filas)',
        'SELECT p.id FROM pedido p JOIN item_pedido ip ON ip.pedido_id = p.id '
        f'LEFT JOIN cupon_uso cu ON cu.pedido_id = p.id WHERE p.tienda_id = {t} AND cu.id IS NULL '
        'GROUP BY p.id, p.total HAVING p.total <> SUM(ip.cantidad * ip.precio_unitario);',
        '```',
        '',
        f'Para deshacerlo: `python manage.py sembrar_datos_sinteticos --empresa {empresa.email} --revertir`',
        '',
    ]
    return '\n'.join(lineas)
