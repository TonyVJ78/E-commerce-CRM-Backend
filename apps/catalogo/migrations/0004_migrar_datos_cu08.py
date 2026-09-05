from decimal import Decimal

from django.db import migrations
from django.utils import timezone
from django.utils.text import slugify


ZERO = Decimal('0')


def limited_unique(value, used, fallback, max_length):
    base = (value or '').strip() or fallback
    base = base[:max_length]
    candidate = base
    suffix = 2

    while candidate in used:
        ending = f'-{suffix}'
        candidate = f'{base[:max_length - len(ending)]}{ending}'
        suffix += 1

    used.add(candidate)
    return candidate


def attribute_key(name, attribute_id, used):
    key = slugify((name or '').strip()).replace('-', '_')
    key = key or f'atributo_{attribute_id}'
    candidate = key
    suffix = 2

    while candidate in used:
        candidate = f'{key}_{suffix}'
        suffix += 1

    used.add(candidate)
    return candidate


def migrate_catalog_data(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Producto = apps.get_model('catalogo', 'Producto')
    Variante = apps.get_model('catalogo', 'Variante')
    Inventario = apps.get_model('catalogo', 'Inventario')
    ImagenProducto = apps.get_model('catalogo', 'ImagenProducto')
    ProductoEtiqueta = apps.get_model('catalogo', 'ProductoEtiqueta')
    VarianteAtributo = apps.get_model('catalogo', 'VarianteAtributo')

    migrated_at = timezone.now()
    used_slugs_by_store = {}

    for producto in Producto.objects.using(db_alias).order_by('id'):
        used_slugs = used_slugs_by_store.setdefault(producto.tienda_id, set())
        slug = limited_unique(
            slugify(producto.nombre),
            used_slugs,
            f'producto-{producto.id}',
            180,
        )

        etiquetas = []
        seen_tags = set()
        for relation in ProductoEtiqueta.objects.using(db_alias).filter(
            producto_id=producto.id,
        ).select_related('etiqueta').order_by('id'):
            nombre = (relation.etiqueta.nombre or '').strip()
            if nombre and nombre not in seen_tags:
                etiquetas.append(nombre)
                seen_tags.add(nombre)

        imagenes = [
            {'url': imagen.url, 'public_id': ''}
            for imagen in ImagenProducto.objects.using(db_alias).filter(
                producto_id=producto.id,
            ).order_by('orden', 'id')
        ]

        Producto.objects.using(db_alias).filter(pk=producto.pk).update(
            slug=slug,
            etiquetas=etiquetas,
            imagenes=imagenes,
            creado=migrated_at,
            actualizado=migrated_at,
        )

        variantes = list(
            Variante.objects.using(db_alias)
            .filter(producto_id=producto.id)
            .order_by('id')
        )
        used_skus = set()

        for variante in variantes:
            inventarios = Inventario.objects.using(db_alias).filter(
                variante_id=variante.id,
            )
            stock = sum((inventario.stock for inventario in inventarios), 0)
            stock_minimos = [
                inventario.umbral_minimo for inventario in inventarios
            ]
            stock_minimo = max(stock_minimos, default=5)

            atributos = {}
            used_attribute_keys = set()
            for relation in VarianteAtributo.objects.using(db_alias).filter(
                variante_id=variante.id,
            ).select_related('atributo').order_by('id'):
                key = attribute_key(
                    relation.atributo.nombre,
                    relation.atributo_id,
                    used_attribute_keys,
                )
                atributos[key] = relation.valor

            precio = (producto.precio_base or ZERO) + (
                variante.precio_adicional or ZERO
            )
            sku = limited_unique(
                variante.sku,
                used_skus,
                producto.sku or f'PROD-{producto.id}',
                60,
            )

            variante.nombre = (variante.nombre or '').strip() or 'Unica'
            variante.sku = sku
            variante.precio = max(precio, ZERO)
            variante.stock = max(stock, 0)
            variante.stock_minimo = max(stock_minimo, 0)
            variante.atributos = atributos
            variante.save(update_fields=[
                'nombre',
                'sku',
                'precio',
                'stock',
                'stock_minimo',
                'atributos',
            ])

        if not variantes:
            sku = limited_unique(
                producto.sku,
                used_skus,
                f'PROD-{producto.id}',
                60,
            )
            Variante.objects.using(db_alias).create(
                producto_id=producto.id,
                tienda_id=producto.tienda_id,
                nombre='Unica',
                precio_adicional=ZERO,
                sku=sku,
                precio=max(producto.precio_base or ZERO, ZERO),
                precio_oferta=None,
                stock=0,
                stock_minimo=5,
                atributos={},
                activa=True,
            )


def reverse_catalog_data(apps, schema_editor):
    # La conversion a JSON no permite reconstruir fielmente las tablas auxiliares.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('catalogo', '0003_alter_producto_actualizado_alter_producto_creado'),
        ('pedidos', '0002_alter_itemcarrito_variante_alter_itempedido_variante'),
    ]

    operations = [
        migrations.RunPython(migrate_catalog_data, reverse_catalog_data),
    ]
