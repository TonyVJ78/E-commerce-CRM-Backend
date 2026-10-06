"""
Script de poblacion de datos multitenant y carga historica de 6 meses.
Asigna tiendas a empresa1 y empresa2, puebla catalogo, inventario,
movimientos de stock, pedidos con variedad de estados y registros de CRM.
"""
import os
import sys
import random
from datetime import timedelta
from decimal import Decimal

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.db import connection, transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.usuarios.models import Usuario
from apps.tiendas.models import Tienda
from apps.catalogo.models import Categoria, Producto, Variante, VarianteStockMovimiento
from apps.pedidos.models import Pedido, ItemPedido, HistorialEstadoPedido, Pago, Envio, DireccionEnvio, MetodoPago
from apps.crm.models import Segmento, FichaCliente, InteraccionCliente

def run():
    print("[1/6] Asignando formalmente tiendas a empresa1 y empresa2...")

    empresa1 = Usuario.objects.get(email='empresa1@kantu.bo')
    empresa2 = Usuario.objects.get(email='empresa2@kantu.bo')

    # Tiendas Textiles -> empresa1
    t3 = Tienda.objects.filter(slug='textiles-los-andes').first()
    t5 = Tienda.objects.filter(slug='textiles-alpaca-andina').first()

    if t3:
        t3.propietario = empresa1
        t3.save(update_fields=['propietario'])
        print(f"Tienda {t3.id} ({t3.nombre}) asignada a {empresa1.email}")

    if t5:
        t5.propietario = empresa1
        t5.save(update_fields=['propietario'])
        print(f"Tienda {t5.id} ({t5.nombre}) asignada a {empresa1.email}")

    # Tiendas Gourmet -> empresa2
    t1 = Tienda.objects.filter(slug='sabores-de-bolivia').first()
    t6 = Tienda.objects.filter(slug='sabores-bolivia-gourmet').first()

    if t1:
        t1.propietario = empresa2
        t1.save(update_fields=['propietario'])
        print(f"Tienda {t1.id} ({t1.nombre}) asignada a {empresa2.email}")

    if t6:
        t6.propietario = empresa2
        t6.save(update_fields=['propietario'])
        print(f"Tienda {t6.id} ({t6.nombre}) asignada a {empresa2.email}")

    # Clientes para compras y CRM
    clientes = list(Usuario.objects.filter(rol__nombre='cliente'))
    if not clientes:
        cliente1 = Usuario.objects.filter(email='cliente1@kantu.bo').first()
        clientes = [cliente1] if cliente1 else []

    print(f"Clientes disponibles: {len(clientes)}")

    # [2/6] Poblar catalogo en Tienda 3 (Textiles Los Andes) si esta vacia
    if t3 and Producto.objects.filter(tienda=t3).count() == 0:
        print("[2/6] Poblando catalogo para Tienda 3 (Textiles Los Andes)...")
        cat_ponchos, _ = Categoria.objects.get_or_create(tienda=t3, nombre="Ponchos y Abrigos")
        cat_aguayos, _ = Categoria.objects.get_or_create(tienda=t3, nombre="Aguayos Tradicionales")
        cat_chompas, _ = Categoria.objects.get_or_create(tienda=t3, nombre="Chompas de Alpaca")
        cat_accesorios, _ = Categoria.objects.get_or_create(tienda=t3, nombre="Accesorios y Chullos")

        productos_textiles = [
            {
                "nombre": "Poncho Imperial de Alpaca Fina Paceno",
                "descripcion": "Poncho tradicional tejido en telar de cuatro estacas con 100% fibra de alpaca seleccionada.",
                "categoria": cat_ponchos,
                "imagenes": [
                    {"url": "https://images.unsplash.com/photo-1516762689617-e1cffcef479d?auto=format&fit=crop&w=800&q=80", "public_id": "poncho-alpaca-1"},
                    {"url": "https://images.unsplash.com/photo-1543163521-1bf539c55dd2?auto=format&fit=crop&w=800&q=80", "public_id": "poncho-alpaca-2"},
                ],
                "variantes": [
                    {"nombre": "Talla M - Color Carmesi", "precio": Decimal("320.00"), "stock": 45, "stock_minimo": 5, "atributos": {"talla": "M", "color": "Carmesi"}},
                    {"nombre": "Talla L - Color Carmesi", "precio": Decimal("340.00"), "stock": 40, "stock_minimo": 5, "atributos": {"talla": "L", "color": "Carmesi"}},
                    {"nombre": "Talla L - Tierra Natural", "precio": Decimal("340.00"), "stock": 35, "stock_minimo": 5, "atributos": {"talla": "L", "color": "Tierra"}},
                ]
            },
            {
                "nombre": "Aguayo Antiguo Ceremonial Multicolor",
                "descripcion": "Pieza textil de coleccion con iconografia andina ancestral de la cultura Jalq'a.",
                "categoria": cat_aguayos,
                "imagenes": [
                    {"url": "https://images.unsplash.com/photo-1607083206869-4c7672e72a8a?auto=format&fit=crop&w=800&q=80", "public_id": "aguayo-multicolor-1"},
                ],
                "variantes": [
                    {"nombre": "Tamano Mediano (1.20m x 1.00m)", "precio": Decimal("240.00"), "stock": 30, "stock_minimo": 4, "atributos": {"tamano": "Mediano"}},
                    {"nombre": "Tamano Grande (1.80m x 1.20m)", "precio": Decimal("310.00"), "stock": 25, "stock_minimo": 4, "atributos": {"tamano": "Grande"}},
                ]
            },
            {
                "nombre": "Chompa Sueter Cuello Alto de Baby Alpaca",
                "descripcion": "Chompa ultra suave con diseno jacquard clasico, maxima proteccion termica.",
                "categoria": cat_chompas,
                "imagenes": [
                    {"url": "https://images.unsplash.com/photo-1620799140408-edc6dcb6d633?auto=format&fit=crop&w=800&q=80", "public_id": "chompa-alpaca-1"},
                ],
                "variantes": [
                    {"nombre": "Talla S - Gris Perla", "precio": Decimal("290.00"), "stock": 25, "stock_minimo": 5, "atributos": {"talla": "S", "color": "Gris"}},
                    {"nombre": "Talla M - Gris Perla", "precio": Decimal("300.00"), "stock": 30, "stock_minimo": 5, "atributos": {"talla": "M", "color": "Gris"}},
                    {"nombre": "Talla L - Vicuna", "precio": Decimal("310.00"), "stock": 28, "stock_minimo": 5, "atributos": {"talla": "L", "color": "Vicuna"}},
                ]
            },
            {
                "nombre": "Chullo Tradicional Andino con Orejeras",
                "descripcion": "Gorro tejido con lana virgen de oveja y alpaca, diseno con motivos tiwanakotas.",
                "categoria": cat_accesorios,
                "imagenes": [
                    {"url": "https://images.unsplash.com/photo-1576871337622-98d48d1cf531?auto=format&fit=crop&w=800&q=80", "public_id": "chullo-andino-1"},
                ],
                "variantes": [
                    {"nombre": "Patron Sol Andino", "precio": Decimal("65.00"), "stock": 50, "stock_minimo": 10, "atributos": {"patron": "Sol Andino"}},
                    {"nombre": "Patron Chakana", "precio": Decimal("65.00"), "stock": 45, "stock_minimo": 10, "atributos": {"patron": "Chakana"}},
                ]
            },
            {
                "nombre": "Chalina Extra Larga de Alpaca y Seda",
                "descripcion": "Chalina de textura ligera y elegante acabado con flecos anudados a mano.",
                "categoria": cat_accesorios,
                "imagenes": [
                    {"url": "https://images.unsplash.com/photo-1520903920243-00d872a2d1c9?auto=format&fit=crop&w=800&q=80", "public_id": "chalina-alpaca-1"},
                ],
                "variantes": [
                    {"nombre": "Azul Indigo", "precio": Decimal("110.00"), "stock": 40, "stock_minimo": 5, "atributos": {"color": "Azul"}},
                    {"nombre": "Vino Tinto", "precio": Decimal("110.00"), "stock": 35, "stock_minimo": 5, "atributos": {"color": "Vino"}},
                ]
            }
        ]

        for p_data in productos_textiles:
            vars_data = p_data.pop("variantes")
            prod = Producto.objects.create(
                tienda=t3,
                slug=f"{slugify(p_data['nombre'])}-{random.randint(100, 999)}",
                activo=True,
                **p_data
            )
            for v_data in vars_data:
                Variante.objects.create(
                    producto=prod,
                    activa=True,
                    sku=f"TLA-{prod.id}-{random.randint(100, 999)}",
                    **v_data
                )
        print(f"Catalogo de Tienda 3 poblado con exito. Total productos: {Producto.objects.filter(tienda=t3).count()}")

    # [3/6] Poblar catalogo en Tienda 1 (Sabores de Bolivia) si esta vacia
    if t1 and Producto.objects.filter(tienda=t1).count() == 0:
        print("[3/6] Poblando catalogo para Tienda 1 (Sabores de Bolivia)...")
        cat_cafes, _ = Categoria.objects.get_or_create(tienda=t1, nombre="Cafes de Altura")
        cat_chocolates, _ = Categoria.objects.get_or_create(tienda=t1, nombre="Chocolates y Cacao")
        cat_infusiones, _ = Categoria.objects.get_or_create(tienda=t1, nombre="Infusiones y Te")
        cat_snacks, _ = Categoria.objects.get_or_create(tienda=t1, nombre="Snacks y Granos")

        productos_sabores = [
            {
                "nombre": "Cafe de Altura Yungas Caranavi (250g)",
                "descripcion": "Cafe de especialidad 100% arabica cultivado a mas de 1.600 msnm con notas citricas y achocolatadas.",
                "categoria": cat_cafes,
                "imagenes": [
                    {"url": "https://images.unsplash.com/photo-1559056199-641a0ac8b55e?auto=format&fit=crop&w=800&q=80", "public_id": "cafe-yungas-1"},
                ],
                "variantes": [
                    {"nombre": "Grano Entero (Tueste Medio)", "precio": Decimal("55.00"), "stock": 60, "stock_minimo": 8, "atributos": {"molienda": "Grano"}},
                    {"nombre": "Molido para Filtro / Chemex", "precio": Decimal("55.00"), "stock": 50, "stock_minimo": 8, "atributos": {"molienda": "Filtro"}},
                    {"nombre": "Molido Fino (Espresso)", "precio": Decimal("58.00"), "stock": 45, "stock_minimo": 8, "atributos": {"molienda": "Espresso"}},
                ]
            },
            {
                "nombre": "Chocolate Silvestre Amazonico 80% Cacao (100g)",
                "descripcion": "Cacao silvestre recolectado a mano en los bosques de Baures, Beni. Sin preservantes ni grasas anadidas.",
                "categoria": cat_chocolates,
                "imagenes": [
                    {"url": "https://images.unsplash.com/photo-1548907040-4baa42d10919?auto=format&fit=crop&w=800&q=80", "public_id": "choco-baures-1"},
                ],
                "variantes": [
                    {"nombre": "Puro 80% Amargo", "precio": Decimal("32.00"), "stock": 70, "stock_minimo": 10, "atributos": {"tipo": "Amargo"}},
                    {"nombre": "Con Sal Rosada de Uyuni", "precio": Decimal("35.00"), "stock": 55, "stock_minimo": 10, "atributos": {"tipo": "Con Sal de Uyuni"}},
                    {"nombre": "Con Nibs Tostados Crocantes", "precio": Decimal("35.00"), "stock": 40, "stock_minimo": 10, "atributos": {"tipo": "Con Nibs"}},
                ]
            },
            {
                "nombre": "Miel Cruda de Abejas Meliponas del Chaco (350g)",
                "descripcion": "Miel virgen no pasteurizada cosechada por comunidades indigenas del Gran Chaco boliviano.",
                "categoria": cat_snacks,
                "imagenes": [
                    {"url": "https://images.unsplash.com/photo-1587049352846-4a222e784d38?auto=format&fit=crop&w=800&q=80", "public_id": "miel-chaco-1"},
                ],
                "variantes": [
                    {"nombre": "Frasco de Vidrio Ambar 350g", "precio": Decimal("48.00"), "stock": 40, "stock_minimo": 6, "atributos": {"presentacion": "350g"}},
                ]
            },
            {
                "nombre": "Mate de Coca y Muna Andina en Bolsitas (Caja x25)",
                "descripcion": "Infusion digestiva natural con hojas de coca seleccionadas y muna de valle alto.",
                "categoria": cat_infusiones,
                "imagenes": [
                    {"url": "https://images.unsplash.com/photo-1576092768241-dec231879fc3?auto=format&fit=crop&w=800&q=80", "public_id": "mate-coca-1"},
                ],
                "variantes": [
                    {"nombre": "Caja 25 Bolsitas Filtrantes", "precio": Decimal("22.00"), "stock": 80, "stock_minimo": 12, "atributos": {"contenido": "25 bolsitas"}},
                ]
            },
            {
                "nombre": "Quinua Real Pop Tostada con Miel (120g)",
                "descripcion": "Grano entero de quinua real del salar inflado y bañado con miel de cana.",
                "categoria": cat_snacks,
                "imagenes": [
                    {"url": "https://images.unsplash.com/photo-1586201375761-83865001e31c?auto=format&fit=crop&w=800&q=80", "public_id": "quinua-pop-1"},
                ],
                "variantes": [
                    {"nombre": "Bolsa Doypack 120g", "precio": Decimal("18.00"), "stock": 90, "stock_minimo": 15, "atributos": {"presentacion": "120g"}},
                ]
            }
        ]

        for p_data in productos_sabores:
            vars_data = p_data.pop("variantes")
            prod = Producto.objects.create(
                tienda=t1,
                slug=f"{slugify(p_data['nombre'])}-{random.randint(100, 999)}",
                activo=True,
                **p_data
            )
            for v_data in vars_data:
                Variante.objects.create(
                    producto=prod,
                    activa=True,
                    sku=f"SDB-{prod.id}-{random.randint(100, 999)}",
                    **v_data
                )
        print(f"Catalogo de Tienda 1 poblado con exito. Total productos: {Producto.objects.filter(tienda=t1).count()}")

    # Desactivar triggers restrictivos de stock y recalculo para insercion historica limpia
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE item_pedido DISABLE TRIGGER trg_actualizar_stock_item_pedido;")
        cursor.execute("ALTER TABLE pedido DISABLE TRIGGER trg_registrar_historial_estado_pedido;")

    try:
        now = timezone.now()
        tiendas_gestion = [t for t in [t3, t5, t1, t6] if t is not None]

        # [4/6] Generar movimientos historicos de stock (6 meses retroactivos)
        print("[4/6] Generando movimientos de stock historicos de 6 meses...")
        motivos = ['ingreso_inicial', 'produccion_taller', 'ajuste_inventario', 'venta_mostrador', 'devolucion_taller']

        for tienda in tiendas_gestion:
            variantes = Variante.objects.filter(producto__tienda=tienda)
            for var in variantes:
                if VarianteStockMovimiento.objects.filter(variante=var).count() < 3:
                    stock_base = var.stock or 30
                    for i in range(6, 0, -1):
                        dias_atras = i * 28 + random.randint(1, 5)
                        fecha_mov = now - timedelta(days=dias_atras)
                        delta = random.choice([15, 20, -5, 10, -2])
                        prev_stock = max(5, stock_base - delta)
                        VarianteStockMovimiento.objects.create(
                            variante=var,
                            previous_stock=prev_stock,
                            delta=delta,
                            resulting_stock=prev_stock + delta,
                            actor=tienda.propietario,
                            reason=random.choice(motivos),
                            created_at=fecha_mov
                        )

        # [5/6] Generar pedidos recibidos con variedad de estados y metricas (CU-22, CU-18)
        print("[5/6] Generando pedidos recibidos con variedad de estados...")
        estados_posibles = ['pendiente', 'en_preparacion', 'enviado', 'entregado', 'cancelado']
        pesos_estados = [0.15, 0.20, 0.20, 0.40, 0.05]

        metodo_pago, _ = MetodoPago.objects.get_or_create(nombre='Tarjeta de Credito / Debito')
        metodo_efectivo, _ = MetodoPago.objects.get_or_create(nombre='Efectivo contra entrega')

        for tienda in tiendas_gestion:
            variantes_tienda = list(Variante.objects.filter(producto__tienda=tienda))
            if not variantes_tienda:
                continue

            pedidos_existentes = Pedido.objects.filter(tienda=tienda).count()
            pedidos_a_crear = max(0, 26 - pedidos_existentes)
            print(f"Tienda {tienda.id} ({tienda.nombre}): {pedidos_existentes} existentes. Creando {pedidos_a_crear} nuevos pedidos...")

            for i in range(pedidos_a_crear):
                cliente = random.choice(clientes)
                # Distribuir fechas: ultimos 7 dias (para dashboard CU-18) y ultimos 6 meses
                if i < 8:
                    dias_atras = random.randint(0, 6)
                else:
                    dias_atras = random.randint(7, 175)

                fecha_pedido = now - timedelta(days=dias_atras, hours=random.randint(1, 18), minutes=random.randint(1, 55))
                estado_elegido = random.choices(estados_posibles, weights=pesos_estados)[0]

                # Crear direccion de envio si no tiene
                dir_envio = DireccionEnvio.objects.filter(cliente=cliente, tienda=tienda).first()
                if not dir_envio:
                    dir_envio = DireccionEnvio.objects.create(
                        cliente=cliente,
                        tienda=tienda,
                        direccion="Av. Arce #2130, Sopocachi",
                        ciudad="La Paz",
                        referencia="Frente a la plaza",
                        es_predeterminada=True
                    )

                # Crear Pedido
                pedido = Pedido.objects.create(
                    cliente=cliente,
                    tienda=tienda,
                    estado_actual=estado_elegido,
                    fecha=fecha_pedido,
                    subtotal=Decimal("0.00"),
                    total=Decimal("0.00")
                )

                # Items del pedido
                vars_seleccionadas = random.sample(variantes_tienda, k=min(len(variantes_tienda), random.randint(1, 3)))
                total_acum = Decimal("0.00")

                for var in vars_seleccionadas:
                    cant = random.randint(1, 2)
                    sub = var.precio * cant
                    total_acum += sub
                    ItemPedido.objects.create(
                        tienda=tienda,
                        pedido=pedido,
                        variante=var,
                        cantidad=cant,
                        precio_unitario=var.precio
                    )

                pedido.subtotal = total_acum
                pedido.total = total_acum
                pedido.save(update_fields=['subtotal', 'total'])

                # Historial de estados
                HistorialEstadoPedido.objects.create(
                    tienda=tienda,
                    pedido=pedido,
                    estado='pendiente',
                    observacion='Pedido recibido en la plataforma.',
                    fecha=fecha_pedido
                )

                if estado_elegido in ['en_preparacion', 'enviado', 'entregado']:
                    HistorialEstadoPedido.objects.create(
                        tienda=tienda,
                        pedido=pedido,
                        estado='en_preparacion',
                        observacion='La tienda comenzo la preparacion del pedido.',
                        fecha=fecha_pedido + timedelta(hours=3)
                    )

                if estado_elegido in ['enviado', 'entregado']:
                    HistorialEstadoPedido.objects.create(
                        tienda=tienda,
                        pedido=pedido,
                        estado='enviado',
                        observacion='Paquete despachado con la empresa de envios.',
                        fecha=fecha_pedido + timedelta(days=1)
                    )

                if estado_elegido == 'entregado':
                    HistorialEstadoPedido.objects.create(
                        tienda=tienda,
                        pedido=pedido,
                        estado='entregado',
                        observacion='Entrega confirmada y recibida por el cliente.',
                        fecha=fecha_pedido + timedelta(days=3)
                    )
                elif estado_elegido == 'cancelado':
                    HistorialEstadoPedido.objects.create(
                        tienda=tienda,
                        pedido=pedido,
                        estado='cancelado',
                        observacion='Pedido cancelado a solicitud del usuario.',
                        fecha=fecha_pedido + timedelta(hours=5)
                    )

                # Registrar Pago
                estado_pago = 'completado' if estado_elegido != 'cancelado' else 'reembolsado'
                if estado_elegido == 'pendiente' and random.random() < 0.3:
                    estado_pago = 'pendiente'

                Pago.objects.create(
                    tienda=tienda,
                    pedido=pedido,
                    metodo_pago=metodo_pago if random.random() > 0.3 else metodo_efectivo,
                    monto=pedido.total,
                    estado=estado_pago,
                    fecha=fecha_pedido,
                    referencia_transaccion=f"PAY-{pedido.id}-{random.randint(10000, 99999)}"
                )

                # Registrar Envio si aplica
                if estado_elegido in ['enviado', 'entregado']:
                    Envio.objects.create(
                        tienda=tienda,
                        pedido=pedido,
                        direccion_envio=dir_envio,
                        transportista="Envios Express Bolivia",
                        numero_seguimiento=f"BOL-{pedido.id}-EXP",
                        fecha_envio=fecha_pedido + timedelta(days=1),
                        fecha_entrega=(fecha_pedido + timedelta(days=3)) if estado_elegido == 'entregado' else None
                    )

        # [6/6] Poblar fichas de CRM e interacciones comerciales (CU-15 / CU-26)
        print("[6/6] Generando fichas de CRM e interacciones comerciales...")
        for tienda in tiendas_gestion:
            seg_vip, _ = Segmento.objects.get_or_create(tienda=tienda, nombre="VIP", defaults={"criterio": "Compras mayores a Bs. 600"})
            seg_frecuente, _ = Segmento.objects.get_or_create(tienda=tienda, nombre="Frecuente", defaults={"criterio": "Al menos 2 pedidos"})
            seg_nuevo, _ = Segmento.objects.get_or_create(tienda=tienda, nombre="Nuevo", defaults={"criterio": "Primer pedido"})

            for cli in clientes:
                total_compras = Pedido.objects.filter(tienda=tienda, cliente=cli).exclude(estado_actual='cancelado').count()
                if total_compras > 0:
                    seg = seg_vip if total_compras >= 3 else (seg_frecuente if total_compras >= 2 else seg_nuevo)
                    ficha, _ = FichaCliente.objects.get_or_create(tienda=tienda, cliente=cli, defaults={"segmento": seg})
                    if ficha.segmento != seg:
                        ficha.segmento = seg
                        ficha.save(update_fields=['segmento'])

                    # Crear interacciones demostrativas si no tiene
                    if InteraccionCliente.objects.filter(tienda=tienda, ficha_cliente=ficha).count() == 0:
                        InteraccionCliente.objects.create(
                            tienda=tienda,
                            ficha_cliente=ficha,
                            tipo="Consulta",
                            mensaje="Cliente consulto disponibilidad de stock y tiempos de entrega a domicilio.",
                            estado="Resuelto"
                        )
                        InteraccionCliente.objects.create(
                            tienda=tienda,
                            ficha_cliente=ficha,
                            tipo="Venta",
                            mensaje="Confirmacion telefonica de envio y satisfaccion con el producto entregado.",
                            estado="Resuelto"
                        )

    finally:
        # Reactivar triggers de base de datos
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE item_pedido ENABLE TRIGGER trg_actualizar_stock_item_pedido;")
            cursor.execute("ALTER TABLE pedido ENABLE TRIGGER trg_registrar_historial_estado_pedido;")

    print("\nProceso de poblacion multitenant e historico completado exitosamente.")

if __name__ == '__main__':
    run()
