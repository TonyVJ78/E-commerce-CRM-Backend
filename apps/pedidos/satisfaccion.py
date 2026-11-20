"""
Métricas de satisfacción de una tienda a partir de sus `Resena`.

Una reseña con `producto` nulo califica a la tienda; con producto, califica ese
producto. Los totales y la distribución cuentan ambas; los rankings, solo las de
producto. `Resena` no apunta a un pedido: un pedido entregado se considera
calificado si su cliente dejó una reseña de la tienda o de alguno de sus productos.
"""

from django.db.models import Avg, Count, Exists, OuterRef, Q
from django.db.models.functions import TruncMonth

from . import estados
from .models import ItemPedido, Pedido, Resena

MINIMO_RESENAS_RANKING = 3
TAMANO_RANKING = 5
ULTIMAS_RESENAS = 20
CALIFICACIONES = range(1, 6)


def _porcentaje(parte, total):
    return round(parte * 100 / total, 1) if total else 0.0


def _promedio(valor):
    return round(float(valor), 2) if valor is not None else None


def resenas_en_rango(tienda, desde, hasta):
    resenas = Resena.objects.filter(tienda=tienda)
    if desde:
        resenas = resenas.filter(fecha__date__gte=desde)
    if hasta:
        resenas = resenas.filter(fecha__date__lte=hasta)
    return resenas


def _resumen(resenas):
    conteos = {c: 0 for c in CALIFICACIONES}
    for fila in resenas.values('calificacion').annotate(n=Count('id')):
        conteos[fila['calificacion']] = fila['n']
    total = sum(conteos.values())
    promedio = resenas.aggregate(p=Avg('calificacion'))['p']
    positivas = conteos[4] + conteos[5]
    neutras = conteos[3]
    negativas = conteos[1] + conteos[2]
    return {
        'total': total,
        'promedio': _promedio(promedio),
        'distribucion': [
            {'estrellas': c, 'cantidad': conteos[c], 'porcentaje': _porcentaje(conteos[c], total)}
            for c in CALIFICACIONES
        ],
        'sentimiento': {
            'positivas': {'cantidad': positivas, 'porcentaje': _porcentaje(positivas, total)},
            'neutras': {'cantidad': neutras, 'porcentaje': _porcentaje(neutras, total)},
            'negativas': {'cantidad': negativas, 'porcentaje': _porcentaje(negativas, total)},
        },
    }


def _tendencia_mensual(resenas):
    filas = (
        resenas.annotate(mes=TruncMonth('fecha'))
        .values('mes')
        .annotate(promedio=Avg('calificacion'), cantidad=Count('id'))
        .order_by('mes')
    )
    return [
        {
            'mes': fila['mes'].strftime('%Y-%m'),
            'promedio': _promedio(fila['promedio']),
            'cantidad': fila['cantidad'],
        }
        for fila in filas
    ]


def _ranking_productos(resenas, minimo):
    por_producto = (
        resenas.filter(producto__isnull=False)
        .values('producto_id', 'producto__nombre')
        .annotate(promedio=Avg('calificacion'), cantidad=Count('id'))
        .filter(cantidad__gte=minimo)
    )

    def a_dict(fila):
        return {
            'producto_id': fila['producto_id'],
            'nombre': fila['producto__nombre'],
            'promedio': _promedio(fila['promedio']),
            'cantidad': fila['cantidad'],
        }

    mejores = por_producto.order_by('-promedio', '-cantidad', 'producto__nombre')[:TAMANO_RANKING]
    peores = por_producto.order_by('promedio', '-cantidad', 'producto__nombre')[:TAMANO_RANKING]
    return [a_dict(f) for f in mejores], [a_dict(f) for f in peores]


def _tasa_de_respuesta(tienda, desde, hasta):
    entregados = Pedido.objects.filter(tienda=tienda, estado_actual=estados.ENTREGADO)
    if desde:
        entregados = entregados.filter(fecha__date__gte=desde)
    if hasta:
        entregados = entregados.filter(fecha__date__lte=hasta)

    resena_de_tienda = Resena.objects.filter(
        tienda=OuterRef('tienda'), cliente=OuterRef('cliente'), producto__isnull=True,
    )
    producto_resenado = ItemPedido.objects.filter(
        pedido=OuterRef('pk'), variante__producto__resenas__cliente=OuterRef('cliente'),
    )
    calificados = entregados.filter(Q(Exists(resena_de_tienda)) | Q(Exists(producto_resenado))).count()
    total = entregados.count()
    return {
        'pedidos_entregados': total,
        'pedidos_calificados': calificados,
        'porcentaje': _porcentaje(calificados, total),
    }


def _a_dict_resena(resena):
    return {
        'id': resena.id,
        'calificacion': resena.calificacion,
        'comentario': resena.comentario,
        'producto': resena.producto.nombre if resena.producto else None,
        'cliente': resena.cliente.first_name or 'Cliente',
        'fecha': resena.fecha.isoformat(),
    }


def ultimas_resenas_con_comentario(resenas, limite):
    con_comentario = resenas.exclude(comentario='').select_related('producto', 'cliente')
    return list(con_comentario.order_by('-fecha', '-id')[:limite])


def panel(tienda, desde, hasta, minimo_ranking=MINIMO_RESENAS_RANKING):
    resenas = resenas_en_rango(tienda, desde, hasta)
    mejores, peores = _ranking_productos(resenas, minimo_ranking)
    return {
        **_resumen(resenas),
        'tendencia_mensual': _tendencia_mensual(resenas),
        'minimo_resenas_ranking': minimo_ranking,
        'productos_mejor_calificados': mejores,
        'productos_peor_calificados': peores,
        'tasa_respuesta': _tasa_de_respuesta(tienda, desde, hasta),
        'ultimas_resenas': [
            _a_dict_resena(r) for r in ultimas_resenas_con_comentario(resenas, ULTIMAS_RESENAS)
        ],
    }
