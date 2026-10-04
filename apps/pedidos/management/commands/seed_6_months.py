"""
Management Command para Kantu Market: Inyectar 6 meses de historial continuo.
Puebla catálogo orgánico de alta calidad con imágenes contextuales por temática,
precios realistas en BOB, stock masivo para pruebas y telemetría de IA.

Uso:
    python manage.py seed_6_months [--purge] [--pedidos=120] [--eventos=350] [--stock=10000]
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.catalogo.models import Categoria, Producto, Variante
from apps.ia.models import EventoUsuario
from apps.pedidos.models import (
    Carrito,
    DireccionEnvio,
    HistorialEstadoPedido,
    ItemCarrito,
    ItemPedido,
    MetodoPago,
    Pago,
    Pedido,
)
from apps.tiendas.models import Tienda
from apps.usuarios.models import Rol, Usuario


class Command(BaseCommand):
    help = 'Puebla la base de datos con 6 meses de historial continuo, catálogo contextual y telemetría rica.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--purge',
            action='store_true',
            help='Purga datos previos de catálogo, pedidos, pagos y telemetría antes de sembrar (mantiene cuentas admin y roles).',
        )
        parser.add_argument(
            '--pedidos',
            type=int,
            default=120,
            help='Número de pedidos a generar en los últimos 6 meses (default: 120)',
        )
        parser.add_argument(
            '--eventos',
            type=int,
            default=350,
            help='Número de eventos de telemetría IA a generar (default: 350)',
        )
        parser.add_argument(
            '--stock',
            type=int,
            default=10000,
            help='Stock inicial masivo por variante para evitar saturación de triggers (default: 10000)',
        )

    def handle(self, *args, **options):
        purge = options['purge']
        total_pedidos_target = options['pedidos']
        total_eventos_target = options['eventos']
        stock_masivo = options['stock']

        self.stdout.write(self.style.NOTICE("=================================================================="))
        self.stdout.write(self.style.NOTICE(">>> KANTU MARKET: SEMBRADO DE 6 MESES CON CATÁLOGO ORGÁNICO"))
        self.stdout.write(self.style.NOTICE(f">>> Config: {total_pedidos_target} pedidos | {total_eventos_target} eventos IA | Stock: {stock_masivo}/var | Purge: {purge}"))
        self.stdout.write(self.style.NOTICE("=================================================================="))

        # 0. Protocolo de Purga Atómica (si se solicitó --purge)
        if purge:
            self.stdout.write(self.style.WARNING(">>> Ejecutando protocolo de purga limpia (pedidos, pagos, telemetría y catálogo)..."))
            with transaction.atomic():
                Pago.objects.all().delete()
                HistorialEstadoPedido.objects.all().delete()
                ItemPedido.objects.all().delete()
                Pedido.objects.all().delete()
                ItemCarrito.objects.all().delete()
                Carrito.objects.all().delete()
                EventoUsuario.objects.all().delete()
                Variante.objects.all().delete()
                Producto.objects.all().delete()
                Categoria.objects.all().delete()
                DireccionEnvio.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("[OK] Base de datos purgada. Cuentas de usuario y roles preservados."))

        # 1. Configuración de Roles
        rol_empresa, _ = Rol.objects.get_or_create(nombre='empresa')
        rol_cliente, _ = Rol.objects.get_or_create(nombre='cliente')

        # 2. Métodos de Pago Oficiales
        metodos_pago_nombres = [
            'Stripe / Tarjeta de Crédito',
            'QR Simple (BCP / BNB / Mercantil)',
            'Pago Contra Entrega',
        ]
        metodo_objs = []
        for nom in metodos_pago_nombres:
            obj, _ = MetodoPago.objects.get_or_create(nombre=nom)
            metodo_objs.append(obj)

        # 3. Definición de Catálogo Orgánico y Contextual por Tienda
        tiendas_config = [
            {
                'email': 'tenant.textiles@kantu.bo',
                'nombre_empresa': 'Textiles & Alpaca Andina',
                'slug': 'textiles-alpaca-andina',
                'descripcion': 'Taller maestro de hilandería y tejeduría en fibra de alpaca, vicuña y tintes naturales del altiplano.',
                'color_primario': '#1A365D',
                'logo_url': 'https://images.unsplash.com/photo-1544816155-12df9643f363?auto=format&fit=crop&w=400&q=80',
                'categorias': [
                    {
                        'nombre': 'Ponchos y Abrigos Andinos',
                        'productos': [
                            {
                                'nombre': 'Poncho Imperial Qhapaq Ñan de Alpaca Fina',
                                'slug': 'poncho-imperial-qhapaq-nan',
                                'descripcion': 'Tejido artesanalmente en telar tradicional de cuatro estacas por maestras tejedoras del altiplano paceño. Confeccionado con 100% fibra de alpaca del primer esquilado (22 micras), ofreciendo una caída noble, aislamiento térmico superior y una textura sedosa que repele la humedad sin provocar picazón. Patrón geométrico ancestral teñido con tintes botánicos de cochinilla y nogal.',
                                'precio': '420.00',
                                'imagenes': [
                                    'https://images.unsplash.com/photo-1516762689617-e1cffcef479d?auto=format&fit=crop&w=800&q=80',
                                    'https://images.unsplash.com/photo-1543163521-1bf539c55dd2?auto=format&fit=crop&w=800&q=80',
                                ],
                                'variantes': ['Talla Única - Azul Colonial', 'Talla Única - Rojo Carmesí', 'Talla Única - Tierra Natural'],
                            },
                            {
                                'nombre': 'Chompa Suéter de Baby Alpaca Trenzado Inglés',
                                'slug': 'sueter-baby-alpaca-trenzado-ingles',
                                'descripcion': 'Suéter térmico tejido en punto trenzado inglés en Oruro. Su hilado doble de baby alpaca garantiza máxima calidez con apenas 480 gramos de peso. Incorpora cuello acanalado elástico, puños reforzados y costuras planas invisibles, ideal para uso urbano o viajes a climas fríos.',
                                'precio': '340.00',
                                'imagenes': [
                                    'https://images.unsplash.com/photo-1620799140408-edc6dcb6d633?auto=format&fit=crop&w=800&q=80',
                                    'https://images.unsplash.com/photo-1434389677669-e08b4cac3105?auto=format&fit=crop&w=800&q=80',
                                ],
                                'variantes': ['Talla M - Gris Perla', 'Talla L - Gris Perla', 'Talla M - Beige Vicuña', 'Talla L - Beige Vicuña'],
                            },
                        ],
                    },
                    {
                        'nombre': 'Accesorios y Complementos',
                        'productos': [
                            {
                                'nombre': 'Chalina Extra Larga de Alpaca y Seda Silvestre',
                                'slug': 'chalina-extra-larga-alpaca-seda',
                                'descripcion': 'Bufanda señorial de 200 x 45 cm rematada con flecos anudados a mano. Mezcla equilibrada de 70% alpaca superfina y 30% seda silvestre que proporciona un brillo sutil, tacto celestial y una caída elegante para atuendos formales.',
                                'precio': '165.00',
                                'imagenes': [
                                    'https://images.unsplash.com/photo-1608256246200-53e635b5b65f?auto=format&fit=crop&w=800&q=80',
                                    'https://images.unsplash.com/photo-1520903920243-00d872a2d1c9?auto=format&fit=crop&w=800&q=80',
                                ],
                                'variantes': ['Azul Índigo', 'Verde Musgo', 'Negro Carbón'],
                            },
                            {
                                'nombre': 'Chullo Tradicional Kallawaya con Orejeras',
                                'slug': 'chullo-tradicional-kallawaya',
                                'descripcion': 'Gorro tradicional con orejeras de protección térmica y pompones artesanales. Tejido en agujas de 1 mm con iconografía andina de la Chakana y forro interno de micropolar hipoalergénico que protege las orejas del viento de altura.',
                                'precio': '75.00',
                                'imagenes': [
                                    'https://images.unsplash.com/photo-1576871337632-b9aef4c17ab9?auto=format&fit=crop&w=800&q=80',
                                    'https://images.unsplash.com/photo-1513104890138-7c749659a591?auto=format&fit=crop&w=800&q=80',
                                ],
                                'variantes': ['Patrón Chakana Multicolor', 'Patrón Sol Andino'],
                            },
                        ],
                    },
                ],
            },
            {
                'email': 'tenant.sabores@kantu.bo',
                'nombre_empresa': 'Sabores de Bolivia Gourmet',
                'slug': 'sabores-bolivia-gourmet',
                'descripcion': 'Selección de microlotes de café de altura de los Yungas, chocolates de cacao silvestre amazónico y delicias originarias.',
                'color_primario': '#742A2A',
                'logo_url': 'https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?auto=format&fit=crop&w=400&q=80',
                'categorias': [
                    {
                        'nombre': 'Cafés y Cacaos de Especialidad',
                        'productos': [
                            {
                                'nombre': 'Café Geisha Especialidad Los Yungas de Caranavi (250g)',
                                'slug': 'cafe-geisha-yungas-caranavi',
                                'descripcion': 'Cosechado a 1,750 m.s.n.m. en la Reserva Ecológica de Caranavi bajo sombra de árboles nativos. Varietal Geisha procesado mediante fermentación anaeróbica de 48 horas y secado lento en camas africanas. Puntuación en taza SCA 87.5 con elegantes notas florales a jazmín, durazno maduro, miel silvestre y final prolongado.',
                                'precio': '135.00',
                                'imagenes': [
                                    'https://images.unsplash.com/photo-1559056199-641a0ac8b55e?auto=format&fit=crop&w=800&q=80',
                                    'https://images.unsplash.com/photo-1498804103079-a6351b050096?auto=format&fit=crop&w=800&q=80',
                                ],
                                'variantes': ['Grano Entero (Tueste Medio)', 'Molido para Filtrados (V60/Chemex)', 'Molido Fino (Espresso)'],
                            },
                            {
                                'nombre': 'Chocolate Silvestre Amazónico de Baures 80% Cacao (100g)',
                                'slug': 'chocolate-silvestre-amazonia-baures',
                                'descripcion': 'Elaborado Bean-to-Bar con cacao criollo 100% silvestre recolectado a mano por familias indígenas en las islas de bosque del Beni en Baures. Endulzado con azúcar de caña orgánica de cosecha local, sin lecitinas ni conservantes artificiales. Sabores intensos a frutos del bosque, dátiles y madera noble.',
                                'precio': '58.00',
                                'imagenes': [
                                    'https://images.unsplash.com/photo-1548907040-4baa42d10919?auto=format&fit=crop&w=800&q=80',
                                    'https://images.unsplash.com/photo-1511381939415-e44015466834?auto=format&fit=crop&w=800&q=80',
                                ],
                                'variantes': ['Puro 80% Amargo', '80% con Sal Rosada de Uyuni', '75% con Nibs Tostados Crocantes'],
                            },
                        ],
                    },
                    {
                        'nombre': 'Despensa e Infusiones Nativas',
                        'productos': [
                            {
                                'nombre': 'Miel Cruda de Abejas Nativas Meliponas del Chaco (350g)',
                                'slug': 'miel-cruda-abejas-meliponas-chaco',
                                'descripcion': 'Miel pura y medicinal sin pasteurizar producida por abejas meliponas sin aguijón en el Gran Chaco boliviano. De consistencia fluida y aroma cítrico balsámico, rica en antioxidantes y enzimas digestivas naturales. Envasada en frasco de vidrio ámbar de conservación botánica.',
                                'precio': '78.00',
                                'imagenes': [
                                    'https://images.unsplash.com/photo-1587049352846-4a222e784d38?auto=format&fit=crop&w=800&q=80',
                                    'https://images.unsplash.com/photo-1589301760014-d929f3979dbc?auto=format&fit=crop&w=800&q=80',
                                ],
                                'variantes': ['Frasco Vidrio Ámbar 350g'],
                            },
                            {
                                'nombre': 'Té Verde Amazónico con Frutas del Trópico y Cedrón (Caja x 25)',
                                'slug': 'te-verde-amazonico-cedron',
                                'descripcion': 'Blend relajante de hojas de cedrón fresco silvestre, cáscaras de asaí liofilizadas y té verde cosechado en los valles templados. Infusión reconfortante para después de las comidas o momentos de descanso.',
                                'precio': '42.00',
                                'imagenes': [
                                    'https://images.unsplash.com/photo-1576092768241-dec231879fc3?auto=format&fit=crop&w=800&q=80',
                                    'https://images.unsplash.com/photo-1597481499750-3e6b22637e12?auto=format&fit=crop&w=800&q=80',
                                ],
                                'variantes': ['Caja 25 Bolsitas Piramidales'],
                            },
                        ],
                    },
                ],
            },
            {
                'email': 'tenant.ceramica@kantu.bo',
                'nombre_empresa': 'Cerámica & Arte del Valle',
                'slug': 'ceramica-arte-valle',
                'descripcion': 'Alfarería artística, jarrones escultóricos y vajilla utilitaria torneada en arcillas locales de Cochabamba.',
                'color_primario': '#234E52',
                'logo_url': 'https://images.unsplash.com/photo-1578749556568-bc2c40e68b61?auto=format&fit=crop&w=400&q=80',
                'categorias': [
                    {
                        'nombre': 'Cerámica Decorativa y Utilitaria',
                        'productos': [
                            {
                                'nombre': 'Jarrón Escultórico de Arcilla Roja y Engobe Mineral (30cm)',
                                'slug': 'jarron-escultorico-arcilla-roja',
                                'descripcion': 'Pieza de diseño torneada a mano con barros extraídos del Valle Alto de Cochabamba. Cocida en horno de leña a 1,050 °C con acabado satinado en engobes minerales ocres y terracotas. Por su proceso de quema artesanal, cada ejemplar adquiere tonalidades de fuego irrepetibles.',
                                'precio': '230.00',
                                'imagenes': [
                                    'https://images.unsplash.com/photo-1612196808214-b8e1d6145a8c?auto=format&fit=crop&w=800&q=80',
                                    'https://images.unsplash.com/photo-1581783342308-f792dbdd27c5?auto=format&fit=crop&w=800&q=80',
                                ],
                                'variantes': ['Mediano (25 cm)', 'Grande (32 cm)'],
                            },
                            {
                                'nombre': 'Juego de 4 Tazas Rústicas de Gres para Café (320ml)',
                                'slug': 'juego-4-tazas-gres-cafe',
                                'descripcion': 'Set de cuatro tazas con asa anatómica reforzada diseñadas para conservar el calor de cafés e infusiones. Interior esmaltado en blanco perla no poroso (100% apto para microondas y lavavajillas) con textura exterior de gres rústico mate.',
                                'precio': '145.00',
                                'imagenes': [
                                    'https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?auto=format&fit=crop&w=800&q=80',
                                    'https://images.unsplash.com/photo-1577937927133-66ef06acdf18?auto=format&fit=crop&w=800&q=80',
                                ],
                                'variantes': ['Esmalte Turquesa Volcánico', 'Esmalte Ceniza de Roble'],
                            },
                            {
                                'nombre': 'Maceta Cilíndrica Esmaltada con Plato de Drenaje (18cm)',
                                'slug': 'maceta-cilindrica-esmaltada-plato',
                                'descripcion': 'Maceta de barro de alta densidad ideal para plantas de interior y suculentas. Incluye orificio inferior y plato recolector a juego para proteger muebles y parquet.',
                                'precio': '85.00',
                                'imagenes': [
                                    'https://images.unsplash.com/photo-1485955900006-10f4d324d411?auto=format&fit=crop&w=800&q=80',
                                    'https://images.unsplash.com/photo-1509423350716-97f9360b4e09?auto=format&fit=crop&w=800&q=80',
                                ],
                                'variantes': ['Verde Salvia Botánico', 'Blanco Arena Caliza'],
                            },
                        ],
                    },
                ],
            },
            {
                'email': 'tenant.moda@kantu.bo',
                'nombre_empresa': 'Moda Altoperuana',
                'slug': 'moda-altoperuana',
                'descripcion': 'Orfebrería en plata boliviana 925, marroquinería en cuero curtido y bolsos con paneles de aguayo antiguo.',
                'color_primario': '#44337A',
                'logo_url': 'https://images.unsplash.com/photo-1535632066927-ab7c9ab60908?auto=format&fit=crop&w=400&q=80',
                'categorias': [
                    {
                        'nombre': 'Joyería Fina en Plata 925',
                        'productos': [
                            {
                                'nombre': 'Aretes de Filigrana Tradicional en Plata 925 con Crisocola',
                                'slug': 'aretes-filigrana-plata-crisocola',
                                'descripcion': 'Obra de alta joyería artesanal potosina creada con hilos de plata fina torsionados y engastados a pulso. La pieza central ostenta una piedra natural de crisocola andina pulida en cabujón con vetas azul celeste. Cierre tipo gancho mariposa antialérgico de plata certificada.',
                                'precio': '290.00',
                                'imagenes': [
                                    'https://images.unsplash.com/photo-1535632066927-ab7c9ab60908?auto=format&fit=crop&w=800&q=80',
                                    'https://images.unsplash.com/photo-1523293182086-7651a899d37f?auto=format&fit=crop&w=800&q=80',
                                ],
                                'variantes': ['Plata Pulida Espejo', 'Plata Envejecida Oxidada'],
                            },
                            {
                                'nombre': 'Prendedor Tupu Andino Ceremonial en Plata y Amatista',
                                'slug': 'prendedor-tupu-andino-amatista',
                                'descripcion': 'Broche monumental repujado a mano en lámina de plata 925 con motivos iconográficos del cóndor andino y flor de cantuta. Aguja reforzada de fijación para mantas o ponchos de lana con engaste de amatista natural de La Gaiba.',
                                'precio': '240.00',
                                'imagenes': [
                                    'https://images.unsplash.com/photo-1602751584552-8ba73aad10e1?auto=format&fit=crop&w=800&q=80',
                                    'https://images.unsplash.com/photo-1599643478518-a784e5dc4c8f?auto=format&fit=crop&w=800&q=80',
                                ],
                                'variantes': ['Amatista Violeta Imperial', 'Citrino Dorado Cálido'],
                            },
                        ],
                    },
                    {
                        'nombre': 'Marroquinería y Cuero con Aguayo',
                        'productos': [
                            {
                                'nombre': 'Bolso Tote de Cuero Vacuno con Panel de Aguayo Jalq’a',
                                'slug': 'bolso-tote-cuero-aguayo-jalqa',
                                'descripcion': 'Bolso de estructura amplia confeccionado en cuero vacuno plena flor teñido en tono caramelo al aceite. El frontis incorpora un panel de tejido tradicional Jalq’a de Chuquisaca con figuras zoomorfas místicas. Interior forrado en loneta de algodón con compartimento acolchado para laptop de 15 pulgadas y herrajes de bronce.',
                                'precio': '480.00',
                                'imagenes': [
                                    'https://images.unsplash.com/photo-1548036328-c9fa89d128fa?auto=format&fit=crop&w=800&q=80',
                                    'https://images.unsplash.com/photo-1590874103328-eac38a683ce7?auto=format&fit=crop&w=800&q=80',
                                ],
                                'variantes': ['Cuero Caramelo Natural', 'Cuero Negro Azabache'],
                            },
                            {
                                'nombre': 'Billetera Bifold de Cuero Flor con Telar Andino y Bloqueo RFID',
                                'slug': 'billetera-cuero-flor-telar-andino',
                                'descripcion': 'Billetera compacta y delgada con 8 ranuras para tarjetas bancarias, compartimento para billetes forrado en tela suave y malla interior de bloqueo de radiofrecuencia (RFID) para máxima seguridad digital.',
                                'precio': '135.00',
                                'imagenes': [
                                    'https://images.unsplash.com/photo-1627123424574-724758594e93?auto=format&fit=crop&w=800&q=80',
                                    'https://images.unsplash.com/photo-1606503837920-569b91c530f2?auto=format&fit=crop&w=800&q=80',
                                ],
                                'variantes': ['Marrón Tabaco', 'Negro Ébano'],
                            },
                        ],
                    },
                ],
            },
        ]

        tiendas_creadas = []
        todas_las_variantes = []
        todos_los_productos = []

        for t_info in tiendas_config:
            user_empresa = Usuario.objects.filter(email=t_info['email']).first()
            if not user_empresa:
                user_empresa = Usuario.objects.create_user(
                    email=t_info['email'],
                    password='Password123!',
                    rol=rol_empresa,
                    first_name=t_info['nombre_empresa'].split()[0],
                    last_name='Admin',
                )

            tienda, _ = Tienda.objects.update_or_create(
                slug=t_info['slug'],
                defaults={
                    'propietario': user_empresa,
                    'nombre': t_info['nombre_empresa'],
                    'descripcion': t_info['descripcion'],
                    'color_primario': t_info['color_primario'],
                    'logo_url': t_info['logo_url'],
                    'activa': True,
                },
            )
            tiendas_creadas.append(tienda)

            # Categorías y Productos con Imágenes Contextuales Enriquecidas
            for cat_info in t_info['categorias']:
                categoria, _ = Categoria.objects.get_or_create(
                    tienda=tienda,
                    nombre=cat_info['nombre'],
                )
                for prod_info in cat_info['productos']:
                    # Mapear lista estructurada de imágenes para JSONField
                    imagenes_json = [
                        {'url': img_url, 'public_id': f"{prod_info['slug']}-{idx + 1}"}
                        for idx, img_url in enumerate(prod_info['imagenes'])
                    ]

                    prod, _ = Producto.objects.update_or_create(
                        tienda=tienda,
                        slug=prod_info['slug'],
                        defaults={
                            'categoria': categoria,
                            'nombre': prod_info['nombre'],
                            'descripcion': prod_info['descripcion'],
                            'imagenes': imagenes_json,
                            'activo': True,
                        },
                    )
                    todos_los_productos.append(prod)

                    # Variantes con STOCK MASIVO (10,000 unidades)
                    for var_nom in prod_info['variantes']:
                        sku = f"{prod.slug[:4].upper()}-{var_nom[:3].upper()}-{random.randint(100, 999)}"
                        variante, _ = Variante.objects.update_or_create(
                            producto=prod,
                            nombre=var_nom,
                            defaults={
                                'sku': sku,
                                'precio': Decimal(prod_info['precio']),
                                'stock': stock_masivo,  # REGLA VITAL: Stock masivo
                                'activa': True,
                            },
                        )
                        todas_las_variantes.append(variante)

        self.stdout.write(self.style.SUCCESS(
            f"[OK] 4 Tiendas configuradas con {len(todos_los_productos)} productos contextuales y {len(todas_las_variantes)} variantes (Stock inicial: {stock_masivo} c/u)."
        ))

        # 4. Creación de Clientes Reales con Direcciones Bolivianas
        clientes_data = [
            ('carlos.mendoza@kantu.bo', 'Carlos', 'Mendoza', 'Av. Arce #2130, Sopocachi, La Paz'),
            ('valeria.roca@kantu.bo', 'Valeria', 'Roca', 'Equipetrol Calle 7 Este #45, Santa Cruz de la Sierra'),
            ('diego.terrazas@kantu.bo', 'Diego', 'Terrazas', 'Calle España #560, Cochabamba'),
            ('mariana.paz@kantu.bo', 'Mariana', 'Paz', 'Calle Junín #120, Sucre'),
            ('rodrigo.quispe@kantu.bo', 'Rodrigo', 'Quispe', 'Av. 6 de Agosto #890, Oruro'),
            ('camila.claros@kantu.bo', 'Camila', 'Claros', 'Av. Las Américas #330, Tarija'),
            ('alejandro.vaca@kantu.bo', 'Alejandro', 'Vaca', 'Av. Busch #1120, Miraflores, La Paz'),
            ('sofia.morales@kantu.bo', 'Sofía', 'Morales', 'Av. San Martín #740, Las Cuadras, Cochabamba'),
        ]

        clientes_creados = []
        for email, fn, ln, direccion in clientes_data:
            cliente = Usuario.objects.filter(email=email).first()
            if not cliente:
                cliente = Usuario.objects.create_user(
                    email=email,
                    password='Password123!',
                    rol=rol_cliente,
                    first_name=fn,
                    last_name=ln,
                )
            clientes_creados.append(cliente)

            # Asignar dirección de entrega en tiendas
            for t in tiendas_creadas:
                DireccionEnvio.objects.get_or_create(
                    cliente=cliente,
                    tienda=t,
                    defaults={'direccion': direccion},
                )

        self.stdout.write(self.style.SUCCESS(f"[OK] {len(clientes_creados)} Clientes registrados con direcciones locales."))

        # 5. Generación de 6 Meses de Pedidos respetando TRIGGERS de PostgreSQL
        self.stdout.write(self.style.NOTICE(f">>> Generando {total_pedidos_target} pedidos transaccionales en ventana de 180 días..."))

        ahora = timezone.now()
        pedidos_generados = 0

        for i in range(total_pedidos_target):
            # Fecha distribuida en los últimos 180 días
            dias_atras = random.randint(1, 180)
            segundos_dia = random.randint(0, 86399)
            fecha_pedido = ahora - timedelta(days=dias_atras, seconds=segundos_dia)

            cliente = random.choice(clientes_creados)
            tienda = random.choice(tiendas_creadas)
            metodo_pago = random.choice(metodo_objs)

            # Determinación de estados según antigüedad
            if dias_atras > 15:
                estado = random.choices(['entregado', 'cancelado'], weights=[93, 7])[0]
            elif dias_atras > 5:
                estado = random.choices(['entregado', 'enviado'], weights=[65, 35])[0]
            else:
                estado = random.choices(['en_preparacion', 'pendiente', 'enviado'], weights=[40, 30, 30])[0]

            variantes_tienda = [v for v in todas_las_variantes if v.producto.tienda_id == tienda.id]
            if not variantes_tienda:
                continue

            num_items = random.randint(1, min(3, len(variantes_tienda)))
            variantes_seleccionadas = random.sample(variantes_tienda, num_items)

            with transaction.atomic():
                # PASO A: Crear el Pedido con subtotal y total en 0.00
                pedido = Pedido.objects.create(
                    cliente=cliente,
                    tienda=tienda,
                    estado_actual=estado,
                    subtotal=Decimal('0.00'),
                    total=Decimal('0.00'),
                )

                # PASO B: Crear ItemPedido (activa trg_actualizar_stock_item_pedido y trg_recalcular_total_pedido)
                for var in variantes_seleccionadas:
                    cantidad = random.randint(1, 3)
                    ItemPedido.objects.create(
                        tienda=tienda,
                        pedido=pedido,
                        variante=var,
                        cantidad=cantidad,
                        precio_unitario=var.precio,
                    )

                # PASO C: REGLA INQUEBRANTABLE -> pedido.refresh_from_db()
                pedido.refresh_from_db()

                # PASO D: Registrar Pago con total recalculado por PostgreSQL
                es_pagado = (estado != 'cancelado')
                ref_pago = (
                    f"STRIPE-PI-{random.randint(10000000, 99999999)}"
                    if 'Stripe' in metodo_pago.nombre
                    else f"BNB-QR-{random.randint(1000000, 9999999)}"
                )
                pago = Pago.objects.create(
                    tienda=tienda,
                    pedido=pedido,
                    metodo_pago=metodo_pago,
                    monto=pedido.total,
                    estado='pagado' if es_pagado else 'fallido',
                    referencia_transaccion=ref_pago,
                )

                # PASO E: Calibrar fechas pasadas en PostgreSQL para timeline continuo
                Pedido.objects.filter(id=pedido.id).update(fecha=fecha_pedido)
                Pago.objects.filter(id=pago.id).update(fecha=fecha_pedido)
                HistorialEstadoPedido.objects.filter(pedido=pedido).update(fecha=fecha_pedido)

            pedidos_generados += 1
            if pedidos_generados % 25 == 0 or pedidos_generados == total_pedidos_target:
                self.stdout.write(f" ... {pedidos_generados}/{total_pedidos_target} pedidos transaccionales inyectados.")

        self.stdout.write(self.style.SUCCESS(f"[OK] {pedidos_generados} Pedidos históricos creados con totales validados por BD."))

        # 6. Telemetría IA (CU-14): Eventos Realistas de Navegación
        self.stdout.write(self.style.NOTICE(f">>> Generando {total_eventos_target} eventos de telemetría IA en ventana de 180 días..."))

        eventos_creados = 0
        terminos_busqueda = [
            'poncho alpaca', 'chalina baby alpaca', 'chullo kallawaya',
            'cafe geisha', 'caranavi', 'chocolate silvestre', 'baures',
            'miel melipona', 'jarron barro', 'tazas gres', 'maceta ceramica',
            'aretes filigrana', 'plata 925', 'tupu andino', 'bolso aguayo'
        ]

        tipos_evento = [
            EventoUsuario.TipoEvento.VIEW,
            EventoUsuario.TipoEvento.VIEW,
            EventoUsuario.TipoEvento.VIEW,
            EventoUsuario.TipoEvento.CLICK,
            EventoUsuario.TipoEvento.CLICK,
            EventoUsuario.TipoEvento.CART,
            EventoUsuario.TipoEvento.SEARCH,
        ]

        with transaction.atomic():
            for _ in range(total_eventos_target):
                dias_atras = random.randint(1, 180)
                segundos_dia = random.randint(0, 86399)
                fecha_evento = ahora - timedelta(days=dias_atras, seconds=segundos_dia)

                cliente = random.choice(clientes_creados)
                tienda = random.choice(tiendas_creadas)
                tipo = random.choice(tipos_evento)

                if tipo == EventoUsuario.TipoEvento.SEARCH:
                    termino = random.choice(terminos_busqueda)
                    ev = EventoUsuario.objects.create(
                        cliente=cliente,
                        tienda=tienda,
                        producto=None,
                        tipo_evento=tipo,
                        termino_busqueda=termino,
                        metadata={'origen': 'catalogo_busqueda', 'device': random.choice(['web_desktop', 'mobile_flutter'])},
                    )
                else:
                    prods_tienda = [p for p in todos_los_productos if p.tienda_id == tienda.id]
                    if not prods_tienda:
                        continue
                    producto = random.choice(prods_tienda)
                    ev = EventoUsuario.objects.create(
                        cliente=cliente,
                        tienda=tienda,
                        producto=producto,
                        tipo_evento=tipo,
                        termino_busqueda='',
                        metadata={'categoria_id': producto.categoria_id, 'device': random.choice(['web_desktop', 'mobile_flutter'])},
                    )

                EventoUsuario.objects.filter(id=ev.id).update(fecha=fecha_evento)
                eventos_creados += 1

        self.stdout.write(self.style.SUCCESS(f"[OK] {eventos_creados} Registros de telemetría inyectados en evento_usuario."))

        # 7. Resumen de Cierre
        self.stdout.write(self.style.NOTICE("=================================================================="))
        self.stdout.write(self.style.SUCCESS(">>> RE-SEMBRADO DE CALIDAD COMPLETADO CON ÉXITO"))
        self.stdout.write(self.style.SUCCESS(f" - Tiendas activas: {Tienda.objects.filter(activa=True).count()}"))
        self.stdout.write(self.style.SUCCESS(f" - Productos con imágenes contextuales: {Producto.objects.count()}"))
        self.stdout.write(self.style.SUCCESS(f" - Variantes con stock: {Variante.objects.count()}"))
        self.stdout.write(self.style.SUCCESS(f" - Pedidos en base de datos: {Pedido.objects.count()}"))
        self.stdout.write(self.style.SUCCESS(f" - Pagos conciliados: {Pago.objects.count()}"))
        self.stdout.write(self.style.SUCCESS(f" - Interacciones IA: {EventoUsuario.objects.count()}"))
        self.stdout.write(self.style.NOTICE("=================================================================="))
