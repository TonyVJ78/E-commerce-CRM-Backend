"""Motor determinístico de recomendaciones personalizadas de CU-14.

No usa IA generativa ni persiste una segunda copia de las compras. Las señales
de compra se leen siempre desde Pedido e ItemPedido.
"""

from collections import defaultdict
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Exists, IntegerField, OuterRef, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.catalogo.models import Producto, Variante
from apps.pedidos.models import ItemCarrito, ItemPedido

from .models import EventoUsuario


DEFAULT_RECOMMENDATION_LIMIT = 8
MAX_RECOMMENDATION_LIMIT = 20
MAX_CANDIDATE_POOL = 200
EVENT_DEDUPLICATION_SECONDS = 30

EVENT_WEIGHTS = {
    EventoUsuario.TipoEvento.VIEW: 2.0,
    EventoUsuario.TipoEvento.CLICK: 4.0,
    EventoUsuario.TipoEvento.CART: 6.0,
}
PURCHASE_WEIGHT = 10.0
CURRENT_CART_WEIGHT = 6.0
SEARCH_MATCH_WEIGHT = 3.0
POPULARITY_WEIGHT = 0.25


@transaction.atomic
def registrar_interaccion(
    *,
    cliente,
    tienda,
    tipo_evento,
    producto=None,
    termino_busqueda='',
):
    """Persiste una señal validada y deduplica repeticiones inmediatas."""

    if producto is not None and producto.tienda_id != tienda.id:
        raise ValueError('El producto no pertenece a la tienda indicada.')

    termino = (termino_busqueda or '').strip().casefold()[:150]
    desde = timezone.now() - timedelta(seconds=EVENT_DEDUPLICATION_SECONDS)
    recientes = EventoUsuario.objects.filter(
        cliente=cliente,
        tienda=tienda,
        producto=producto,
        tipo_evento=tipo_evento,
        termino_busqueda=termino,
        fecha__gte=desde,
    )
    existente = recientes.order_by('-fecha').first()
    if existente is not None:
        return existente

    return EventoUsuario.objects.create(
        cliente=cliente,
        tienda=tienda,
        producto=producto,
        tipo_evento=tipo_evento,
        termino_busqueda=termino,
    )


def _candidate_queryset(tienda):
    variante_disponible = Variante.objects.filter(
        producto_id=OuterRef('pk'),
        activa=True,
        stock__gt=0,
    )
    return Producto.objects.filter(
        tienda=tienda,
        tienda__activa=True,
        activo=True,
    ).filter(Exists(variante_disponible))


def _purchase_rows(cliente, tienda):
    return ItemPedido.objects.filter(
        pedido__cliente=cliente,
        pedido__tienda=tienda,
        tienda=tienda,
    ).exclude(
        pedido__estado_actual__iexact='cancelado',
    ).values(
        'variante__producto_id',
        'variante__producto__categoria_id',
    ).annotate(total=Sum('cantidad'))


def _cart_rows(cliente, tienda):
    return ItemCarrito.objects.filter(
        carrito__cliente=cliente,
        carrito__tienda=tienda,
        tienda=tienda,
    ).values(
        'variante__producto_id',
        'variante__producto__categoria_id',
    ).annotate(total=Sum('cantidad'))


def obtener_recomendaciones_cliente(*, cliente, tienda, limit=DEFAULT_RECOMMENDATION_LIMIT):
    """Devuelve productos ordenados por afinidad personal y fallback estable."""

    limit = max(1, min(int(limit), MAX_RECOMMENDATION_LIMIT))
    product_scores = defaultdict(float)
    category_scores = defaultdict(float)
    preferred_product_ids = set()
    preferred_category_ids = set()

    event_rows = EventoUsuario.objects.filter(
        cliente=cliente,
        tienda=tienda,
        producto__isnull=False,
        tipo_evento__in=EVENT_WEIGHTS.keys(),
    ).values(
        'producto_id',
        'producto__categoria_id',
        'tipo_evento',
    ).annotate(total=Count('id'))

    for row in event_rows:
        product_id = row['producto_id']
        category_id = row['producto__categoria_id']
        value = EVENT_WEIGHTS[row['tipo_evento']] * row['total']
        product_scores[product_id] += value
        preferred_product_ids.add(product_id)
        if category_id is not None:
            category_scores[category_id] += value * 0.5
            preferred_category_ids.add(category_id)

    for row in _purchase_rows(cliente, tienda):
        product_id = row['variante__producto_id']
        category_id = row['variante__producto__categoria_id']
        quantity = row['total'] or 0
        product_scores[product_id] += PURCHASE_WEIGHT * quantity
        preferred_product_ids.add(product_id)
        if category_id is not None:
            category_scores[category_id] += (PURCHASE_WEIGHT * 0.6) * quantity
            preferred_category_ids.add(category_id)

    for row in _cart_rows(cliente, tienda):
        product_id = row['variante__producto_id']
        category_id = row['variante__producto__categoria_id']
        quantity = row['total'] or 0
        product_scores[product_id] += CURRENT_CART_WEIGHT * quantity
        preferred_product_ids.add(product_id)
        if category_id is not None:
            category_scores[category_id] += (CURRENT_CART_WEIGHT * 0.5) * quantity
            preferred_category_ids.add(category_id)

    search_terms = list(dict.fromkeys(
        EventoUsuario.objects.filter(
            cliente=cliente,
            tienda=tienda,
            tipo_evento=EventoUsuario.TipoEvento.SEARCH,
        ).exclude(termino_busqueda='').values_list(
            'termino_busqueda', flat=True
        )[:50]
    ))[:20]

    base = _candidate_queryset(tienda)
    personal_filter = Q(pk__in=preferred_product_ids)
    if preferred_category_ids:
        personal_filter |= Q(categoria_id__in=preferred_category_ids)
    for term in search_terms:
        personal_filter |= (
            Q(nombre__icontains=term)
            | Q(descripcion__icontains=term)
            | Q(categoria__nombre__icontains=term)
            | Q(etiquetas__contains=[term])
        )

    personal_ids = list(
        base.filter(personal_filter)
        .order_by('-creado', '-id')
        .values_list('id', flat=True)[:100]
    ) if (preferred_product_ids or preferred_category_ids or search_terms) else []

    fallback_ids = list(
        base.annotate(
            compras=Coalesce(
                Sum(
                    'variantes__items_pedido__cantidad',
                    filter=~Q(
                        variantes__items_pedido__pedido__estado_actual__iexact='cancelado'
                    ),
                ),
                Value(0),
                output_field=IntegerField(),
            )
        ).order_by('-compras', '-creado', '-id')
        .values_list('id', flat=True)[:MAX_CANDIDATE_POOL]
    )

    candidate_ids = list(dict.fromkeys(personal_ids + fallback_ids))
    if not candidate_ids:
        return []

    active_variants = Variante.objects.filter(
        activa=True,
        stock__gt=0,
    ).order_by('precio', 'id')
    products = list(
        base.filter(pk__in=candidate_ids)
        .select_related('tienda', 'categoria')
        .prefetch_related(Prefetch('variantes', queryset=active_variants))
    )

    popularity = {
        row['variante__producto_id']: row['total'] or 0
        for row in ItemPedido.objects.filter(
            tienda=tienda,
            variante__producto_id__in=candidate_ids,
        ).exclude(
            pedido__estado_actual__iexact='cancelado',
        ).values('variante__producto_id').annotate(total=Sum('cantidad'))
    }

    lowered_terms = [term.casefold() for term in search_terms if term.strip()]
    final_scores = {}
    for product in products:
        score = product_scores[product.id]
        if product.categoria_id is not None:
            score += category_scores[product.categoria_id]

        searchable = ' '.join([
            product.nombre,
            product.descripcion,
            product.categoria.nombre if product.categoria else '',
            ' '.join(product.etiquetas or []),
        ]).casefold()
        score += sum(
            SEARCH_MATCH_WEIGHT for term in lowered_terms if term in searchable
        )
        score += popularity.get(product.id, 0) * POPULARITY_WEIGHT
        final_scores[product.id] = score

    products.sort(
        key=lambda product: (
            -final_scores[product.id],
            -popularity.get(product.id, 0),
            -product.creado.timestamp(),
            -product.id,
        )
    )
    return products[:limit]
