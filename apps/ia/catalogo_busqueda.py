"""
Búsqueda en el catálogo público para el chatbot de recomendaciones.

La búsqueda por texto se hace en Python y no con `icontains`: así no importan
las tildes ("ceramica" encuentra "Cerámica"), los plurales ("chompas" encuentra
"Chompa") ni el orden de las palabras, y se pueden sumar puntos según dónde
aparece cada palabra. La base sólo filtra lo que es exacto (precio, stock,
producto y tienda activos) y devuelve columnas livianas con `values()`.
"""

import re
import unicodedata
from decimal import Decimal

from django.db.models import Min, Prefetch, Q, Sum
from django.db.models.functions import Coalesce

from apps.catalogo.models import Categoria, Producto, Variante
from apps.tiendas.models import Tienda


LIMITE_RESULTADOS = 8
LIMITE_DESCRIPCION = 160

# Palabras que no ayudan a encontrar un producto. Se comparan ya normalizadas.
PALABRAS_VACIAS = {
    'a', 'al', 'algo', 'algun', 'alguna', 'alguno', 'busco', 'como', 'con', 'cual',
    'de', 'del', 'el', 'en', 'es', 'esta', 'este', 'hay', 'la', 'las', 'lo', 'los',
    'mas', 'me', 'mi', 'mis', 'muy', 'necesito', 'o', 'para', 'por', 'que', 'quiero',
    'se', 'sin', 'su', 'sus', 'tienen', 'tu', 'un', 'una', 'unas', 'uno', 'unos', 'y',
}

# Dónde aparece la palabra pesa distinto: el nombre manda.
PESO_NOMBRE = 3
PESO_CATEGORIA = 2
PESO_ETIQUETA = 2
PESO_DESCRIPCION = 1
PESO_TIENDA = 1


def normalizar(texto):
    """Minúsculas, sin tildes y sin signos: 'Cerámica, ¡Única!' → 'ceramica unica'."""
    sin_tildes = unicodedata.normalize('NFKD', texto or '')
    sin_tildes = ''.join(c for c in sin_tildes if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9ñ]+', ' ', sin_tildes.lower()).strip()


def _raiz(palabra):
    """Quita el plural más común para que 'chompas' y 'chompa' coincidan."""
    if len(palabra) > 4 and palabra.endswith('es'):
        return palabra[:-2]
    if len(palabra) > 3 and palabra.endswith('s'):
        return palabra[:-1]
    return palabra


def terminos_de(consulta):
    vistos = []
    for palabra in normalizar(consulta).split():
        if palabra in PALABRAS_VACIAS or len(palabra) < 2:
            continue
        raiz = _raiz(palabra)
        if raiz not in vistos:
            vistos.append(raiz)
    return vistos


def _puntaje(fila, terminos):
    campos = (
        (normalizar(fila['nombre']), PESO_NOMBRE),
        (normalizar(fila['categoria__nombre']), PESO_CATEGORIA),
        (normalizar(' '.join(fila['etiquetas'] or [])), PESO_ETIQUETA),
        (normalizar(fila['descripcion']), PESO_DESCRIPCION),
        (normalizar(fila['tienda__nombre']), PESO_TIENDA),
    )
    total = 0
    for termino in terminos:
        total += sum(peso for texto, peso in campos if termino in texto)
    return total


def _a_decimal(valor):
    if valor is None or valor == '':
        return None
    try:
        return Decimal(str(valor))
    except Exception:
        return None


def _catalogo_base():
    """Productos visibles para el cliente con su precio efectivo y stock total."""
    activas = Q(variantes__activa=True)
    return (
        Producto.objects
        .filter(activo=True, tienda__activa=True)
        .annotate(
            precio_min=Min(Coalesce('variantes__precio_oferta', 'variantes__precio'), filter=activas),
            stock_total=Sum('variantes__stock', filter=activas),
        )
        .filter(precio_min__isnull=False)
    )


def buscar_productos(
    consulta='',
    categoria='',
    tienda='',
    precio_min=None,
    precio_max=None,
    solo_disponibles=True,
    orden='relevancia',
    limite=LIMITE_RESULTADOS,
):
    """Devuelve `(total_encontrados, [Producto, ...])` ordenados según `orden`."""
    qs = _catalogo_base()

    minimo = _a_decimal(precio_min)
    maximo = _a_decimal(precio_max)
    if minimo is not None:
        qs = qs.filter(precio_min__gte=minimo)
    if maximo is not None:
        qs = qs.filter(precio_min__lte=maximo)
    if solo_disponibles:
        qs = qs.filter(stock_total__gt=0)

    filas = list(qs.values(
        'id', 'nombre', 'descripcion', 'etiquetas', 'categoria__nombre',
        'tienda__nombre', 'precio_min',
    ))

    # Categoría y tienda llegan como texto libre del modelo ("textiles",
    # "Alpaca Andina"); se comparan normalizadas y por inclusión.
    categoria_norm = normalizar(categoria)
    if categoria_norm:
        filas = [f for f in filas if categoria_norm in normalizar(f['categoria__nombre'])]
    tienda_norm = normalizar(tienda)
    if tienda_norm:
        filas = [f for f in filas if tienda_norm in normalizar(f['tienda__nombre'])]

    terminos = terminos_de(consulta)
    if terminos:
        puntuadas = [(f, _puntaje(f, terminos)) for f in filas]
        puntuadas = [(f, p) for f, p in puntuadas if p > 0]
    else:
        puntuadas = [(f, 0) for f in filas]

    if orden == 'precio_asc':
        puntuadas.sort(key=lambda par: (par[0]['precio_min'], -par[1]))
    elif orden == 'precio_desc':
        puntuadas.sort(key=lambda par: (-par[0]['precio_min'], -par[1]))
    else:
        # A igual puntaje, primero lo más nuevo (mayor id), como el catálogo.
        puntuadas.sort(key=lambda par: (-par[1], -par[0]['id']))

    ids = [f['id'] for f, _ in puntuadas[:limite]]
    return len(puntuadas), productos_por_ids(ids)


def productos_por_ids(ids):
    """Productos visibles con sus variantes activas, en el orden de `ids`."""
    if not ids:
        return []
    variantes_activas = Variante.objects.filter(activa=True).order_by('precio', 'id')
    encontrados = (
        _catalogo_base()
        .filter(id__in=ids)
        .select_related('tienda', 'categoria')
        .prefetch_related(Prefetch('variantes', queryset=variantes_activas))
    )
    por_id = {p.id: p for p in encontrados}
    return [por_id[i] for i in ids if i in por_id]


def resumen_para_modelo(producto, con_variantes=False):
    """Lo que el modelo necesita para recomendar: corto y sin URLs de imagen."""
    variantes = list(producto.variantes.all())
    precios_lista = [v.precio for v in variantes]
    datos = {
        'id': producto.id,
        'nombre': producto.nombre,
        'tienda': producto.tienda.nombre,
        'categoria': producto.categoria.nombre if producto.categoria else '',
        'precio_bs': str(producto.precio_min),
        'stock_total': producto.stock_total or 0,
        'descripcion': (producto.descripcion or '')[:LIMITE_DESCRIPCION],
    }
    # Si el precio efectivo es menor que el de lista, hay una oferta vigente.
    if precios_lista and min(precios_lista) > producto.precio_min:
        datos['precio_antes_bs'] = str(min(precios_lista))
    if producto.etiquetas:
        datos['etiquetas'] = producto.etiquetas[:6]

    if con_variantes:
        datos['variantes'] = [
            {
                'nombre': v.nombre,
                'precio_bs': str(v.precio_oferta if v.precio_oferta is not None else v.precio),
                'stock': v.stock,
                'atributos': v.atributos or {},
            }
            for v in variantes
        ]
    elif len(variantes) > 1:
        datos['opciones'] = [v.nombre for v in variantes[:6]]
    return datos


def contexto_catalogo():
    """Categorías y tiendas con productos visibles, para orientar las preguntas."""
    visibles = Q(productos__activo=True, tienda__activa=True)
    categorias = sorted({
        nombre for nombre in
        Categoria.objects.filter(visibles).values_list('nombre', flat=True).distinct()
    }, key=normalizar)
    tiendas = list(
        Tienda.objects.filter(activa=True, productos__activo=True)
        .values_list('nombre', flat=True).distinct().order_by('nombre')
    )
    return categorias[:60], tiendas[:40]
