"""Carga idempotente de datos demo para desarrollo.

Requiere las credenciales de Cloudinary en .env antes de ejecutar cualquier
escritura. No se ejecuta automaticamente desde el arranque del backend.
"""

import os
from decimal import Decimal

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import transaction

from apps.catalogo.models import Categoria, Producto, Variante
from apps.catalogo.services import (
    CloudinaryConfigurationError,
    _cloudinary_uploader,
)
from apps.tiendas.models import Tienda
from apps.usuarios.models import Rol, Usuario


DEMO_PASSWORD = 'Password123!'

USERS = [
    {
        'email': 'admin@kantu.bo',
        'rol': 'administrador',
        'first_name': 'Administrador',
        'last_name': 'Sistema',
        'is_staff': True,
        'is_superuser': True,
    },
    {
        'email': 'empresa@kantu.bo',
        'rol': 'empresa',
        'first_name': 'Carlos',
        'last_name': 'Mamani',
        'is_staff': False,
        'is_superuser': False,
    },
    {
        'email': 'cliente@kantu.bo',
        'rol': 'cliente',
        'first_name': 'Ana',
        'last_name': 'Perez',
        'is_staff': False,
        'is_superuser': False,
    },
    {
        'email': 'empresa2@kantu.bo',
        'rol': 'empresa',
        'first_name': 'Lucia',
        'last_name': 'Quispe',
        'is_staff': False,
        'is_superuser': False,
    },
]

STORES = [
    {
        'owner': 'empresa@kantu.bo',
        'slug': 'artesanias-bolivianas',
        'name': 'Artesanias Bolivianas',
        'description': 'Textiles y artesanias andinas de Bolivia.',
    },
    {
        'owner': 'empresa@kantu.bo',
        'slug': 'kantu-moda-andina',
        'name': 'Kantu Moda Andina',
        'description': 'Ropa artesanal contemporanea.',
    },
    {
        'owner': 'empresa2@kantu.bo',
        'slug': 'arte-de-lucia',
        'name': 'Arte de Lucia',
        'description': 'Tienda de prueba para aislamiento multitenant.',
    },
]

PRODUCTS = [
    {
        'store_slug': 'artesanias-bolivianas',
        'category': 'Accesorios',
        'slug': 'bolso-tejido-andino',
        'name': 'Bolso tejido andino',
        'description': 'Bolso tejido a mano con motivos andinos.',
        'tags': ['artesanal', 'accesorios'],
        'image_public_id': 'kantu/demo/productos/bolso-tejido-andino',
        'image_source': 'https://images.unsplash.com/photo-1553062407-98eeb64c6a62',
        'variants': [
            {
                'sku': 'BOL-AND-UNICA',
                'name': 'Unica',
                'price': '180.00',
                'stock': 12,
                'stock_min': 5,
                'attributes': {},
            },
        ],
    },
    {
        'store_slug': 'artesanias-bolivianas',
        'category': 'Ropa',
        'slug': 'polera-kantu',
        'name': 'Polera Kantu',
        'description': 'Polera artesanal de algodon.',
        'tags': ['artesanal', 'ropa'],
        'image_public_id': 'kantu/demo/productos/polera-kantu',
        'image_source': 'https://images.unsplash.com/photo-1523381210434-271e8be1f52b',
        'variants': [
            {
                'sku': 'POL-RO-S',
                'name': 'Rojo / S',
                'price': '110.00',
                'stock': 4,
                'stock_min': 3,
                'attributes': {'color': 'Rojo', 'talla': 'S'},
            },
            {
                'sku': 'POL-RO-M',
                'name': 'Rojo / M',
                'price': '120.00',
                'sale_price': '99.90',
                'stock': 0,
                'stock_min': 3,
                'attributes': {'color': 'Rojo', 'talla': 'M'},
            },
            {
                'sku': 'POL-NE-L',
                'name': 'Negro / L',
                'price': '125.00',
                'stock': 2,
                'stock_min': 3,
                'attributes': {'color': 'Negro', 'talla': 'L'},
            },
        ],
    },
    {
        'store_slug': 'kantu-moda-andina',
        'category': 'Ropa',
        'slug': 'chompa-de-alpaca',
        'name': 'Chompa de alpaca',
        'description': 'Chompa abrigada de fibra de alpaca.',
        'tags': ['alpaca', 'ropa'],
        'image_public_id': 'kantu/demo/productos/chompa-de-alpaca',
        'image_source': 'https://images.unsplash.com/photo-1517841905240-472988babdf9',
        'variants': [
            {
                'sku': 'CHO-ALP-S',
                'name': 'S',
                'price': '260.00',
                'stock': 0,
                'stock_min': 2,
                'attributes': {'talla': 'S', 'material': 'Alpaca'},
            },
            {
                'sku': 'CHO-ALP-M',
                'name': 'M',
                'price': '270.00',
                'stock': 0,
                'stock_min': 2,
                'attributes': {'talla': 'M', 'material': 'Alpaca'},
            },
            {
                'sku': 'CHO-ALP-L',
                'name': 'L',
                'price': '280.00',
                'stock': 0,
                'stock_min': 2,
                'attributes': {'talla': 'L', 'material': 'Alpaca'},
            },
        ],
    },
    {
        'store_slug': 'kantu-moda-andina',
        'category': 'Hogar',
        'slug': 'manta-artesanal',
        'name': 'Manta artesanal',
        'description': 'Manta decorativa tejida a mano.',
        'tags': ['hogar', 'artesanal'],
        'image_public_id': 'kantu/demo/productos/manta-artesanal',
        'image_source': 'https://images.unsplash.com/photo-1544966503-7cc5ac882d5f',
        'variants': [
            {
                'sku': 'MAN-ART-UNICA',
                'name': 'Unica',
                'price': '320.00',
                'stock': 2,
                'stock_min': 5,
                'attributes': {'material': 'Alpaca'},
            },
        ],
    },
    {
        'store_slug': 'arte-de-lucia',
        'category': 'Decoracion',
        'slug': 'ceramica-andina-demo',
        'name': 'Ceramica andina demo',
        'description': 'Producto de otra empresa para probar aislamiento.',
        'tags': ['demo', 'ceramica'],
        'image_public_id': 'kantu/demo/productos/ceramica-andina-demo',
        'image_source': 'https://images.unsplash.com/photo-1610701596007-11502861dcfa',
        'variants': [
            {
                'sku': 'CER-AND-UNICA',
                'name': 'Unica',
                'price': '95.00',
                'stock': 6,
                'stock_min': 2,
                'attributes': {'material': 'Ceramica'},
            },
        ],
    },
]


def upsert_user(data, roles, summary):
    rol = roles[data['rol']]
    user = Usuario.objects.filter(email=data['email']).first()
    created = user is None
    if created:
        user = Usuario(email=data['email'])

    user.rol = rol
    user.first_name = data['first_name']
    user.last_name = data['last_name']
    user.is_staff = data['is_staff']
    user.is_superuser = data['is_superuser']
    user.activo = True
    user.set_password(DEMO_PASSWORD)
    user.save()
    summary['usuarios_creados' if created else 'usuarios_actualizados'] += 1
    return user


def get_or_update_store(data, users, summary):
    store, created = Tienda.objects.update_or_create(
        propietario=users[data['owner']],
        slug=data['slug'],
        defaults={
            'nombre': data['name'],
            'descripcion': data['description'],
            'activa': True,
        },
    )
    summary['tiendas_creadas' if created else 'tiendas_actualizadas'] += 1
    return store


def get_or_update_category(store, name, summary):
    category, created = Categoria.objects.get_or_create(
        tienda=store,
        nombre=name,
    )
    summary['categorias_creadas' if created else 'categorias_existentes'] += 1
    return category


def cloudinary_demo_image(uploader, public_id, source_url):
    try:
        import cloudinary.api

        resource = cloudinary.api.resource(public_id, resource_type='image')
        return {
            'url': resource.get('secure_url', ''),
            'public_id': public_id,
        }
    except Exception:
        result = uploader.upload(
            source_url,
            public_id=public_id,
            resource_type='image',
            overwrite=False,
            unique_filename=False,
        )
        return {
            'url': result.get('secure_url', ''),
            'public_id': result.get('public_id', public_id),
        }


def upsert_product(data, stores, categories, uploader, summary):
    store = stores[data['store_slug']]
    category = categories[(data['store_slug'], data['category'])]
    image = cloudinary_demo_image(
        uploader,
        data['image_public_id'],
        data['image_source'],
    )

    with transaction.atomic():
        product, created = Producto.objects.update_or_create(
            tienda=store,
            slug=data['slug'],
            defaults={
                'categoria': category,
                'nombre': data['name'],
                'descripcion': data['description'],
                'etiquetas': data['tags'],
                'imagenes': [image],
                'activo': True,
            },
        )
        summary['productos_creados' if created else 'productos_actualizados'] += 1

        for variant_data in data['variants']:
            defaults = {
                'nombre': variant_data['name'],
                'precio': Decimal(variant_data['price']),
                'precio_oferta': (
                    Decimal(variant_data['sale_price'])
                    if variant_data.get('sale_price') is not None else None
                ),
                'stock': variant_data['stock'],
                'stock_minimo': variant_data['stock_min'],
                'atributos': variant_data['attributes'],
                'activa': True,
            }
            _, variant_created = Variante.objects.update_or_create(
                producto=product,
                sku=variant_data['sku'],
                defaults=defaults,
            )
            summary['variantes_creadas' if variant_created else 'variantes_actualizadas'] += 1


def main():
    try:
        uploader = _cloudinary_uploader()
    except CloudinaryConfigurationError as exc:
        raise SystemExit(f'No se puede ejecutar seed_demo.py: {exc}')

    summary = {
        'usuarios_creados': 0,
        'usuarios_actualizados': 0,
        'tiendas_creadas': 0,
        'tiendas_actualizadas': 0,
        'categorias_creadas': 0,
        'categorias_existentes': 0,
        'productos_creados': 0,
        'productos_actualizados': 0,
        'variantes_creadas': 0,
        'variantes_actualizadas': 0,
    }

    roles = {
        nombre: Rol.objects.get_or_create(nombre=nombre)[0]
        for nombre in {'administrador', 'empresa', 'cliente'}
    }
    users = {
        data['email']: upsert_user(data, roles, summary)
        for data in USERS
    }
    stores = {
        data['slug']: get_or_update_store(data, users, summary)
        for data in STORES
    }
    categories = {}
    for data in PRODUCTS:
        store = stores[data['store_slug']]
        key = (data['store_slug'], data['category'])
        if key not in categories:
            categories[key] = get_or_update_category(
                store,
                data['category'],
                summary,
            )

    for data in PRODUCTS:
        upsert_product(data, stores, categories, uploader, summary)

    print('Datos demo procesados correctamente:')
    for key, value in summary.items():
        print(f'- {key}: {value}')
    print('Credenciales demo: Password123! (solo desarrollo)')


if __name__ == '__main__':
    main()
