# -*- coding: utf-8 -*-
"""Genera E-commerce-CRM-Backend/seed_empresas.sql (catalogo demo grande).

Salida: SQL puro, ASCII, idempotente. No se ejecuta contra la BD, solo escribe
el archivo. Editar aqui las listas y volver a correr para regenerar.
"""
import io
import os
import re
import unicodedata

PASSWORD_HASH = (
    "pbkdf2_sha256$870000$KcLpbH6MM9wGs6RPDjxWbD$"
    "7p/ETMzaYAKjYYsXm5F6O4vZpT7fEvtURZSnr20DT6U="
)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_empresas.sql")


def fold(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.replace("\u00f1", "n").replace("\u00d1", "N")


def q(s):
    return "'" + fold(s).replace("'", "''") + "'"


def slugify(s):
    s = fold(s).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------
EMPRESAS = [
    ("Maria", "Condori", "empresa1@kantu.bo"),
    ("Jorge", "Vargas", "empresa2@kantu.bo"),
    ("Rosa", "Flores", "empresa3@kantu.bo"),
    ("David", "Mamani", "empresa4@kantu.bo"),
]
CLIENTES = [
    ("Lucia", "Rojas", "cliente1@kantu.bo"),
    ("Pedro", "Gutierrez", "cliente2@kantu.bo"),
    ("Carla", "Ticona", "cliente3@kantu.bo"),
    ("Marco", "Antezana", "cliente4@kantu.bo"),
    ("Elena", "Choque", "cliente5@kantu.bo"),
    ("Ruben", "Salazar", "cliente6@kantu.bo"),
]

# ---------------------------------------------------------------------------
# Tiendas + catalogo
#   producto: (categoria, nombre, precio_base, tags, variantes)
#     variantes: None                       -> una variante "Unica" a precio_base
#                [(sufijo, {attrs}, precio)] -> varias variantes
# ---------------------------------------------------------------------------
STORES = [
    dict(
        slug="textiles-los-andes", nombre="Textiles Los Andes", color="#C8102E",
        owner="empresa1@kantu.bo", ciudad="La Paz",
        direccion="Calle Sagarnaga 245", telefono="+591 71234567",
        descripcion=("Aguayos, ponchos, chompas y accesorios tejidos a mano en "
                     "La Paz con lana de alpaca y oveja."),
        desc_tpl="{n}. Tejido a mano en {c} con fibras naturales.",
        prefix="TLA",
        productos=[
            ("Aguayos", "Aguayo tradicional paceno", 180, "aguayo,tejido,artesanal", None),
            ("Aguayos", "Aguayo grande multicolor", 240, "aguayo,telar,artesanal", None),
            ("Aguayos", "Aguayo ceremonial rojo", 320, "aguayo,ceremonial", None),
            ("Aguayos", "Q'ipina para cargar", 150, "aguayo,portabebe", None),
            ("Ponchos", "Poncho de alpaca cafe", 320, "poncho,alpaca,abrigo",
             [("Talla M", {"talla": "M"}, 320), ("Talla L", {"talla": "L"}, 340),
              ("Talla XL", {"talla": "XL"}, 360)]),
            ("Ponchos", "Poncho de lana gris", 260, "poncho,lana",
             [("Talla M", {"talla": "M"}, 260), ("Talla L", {"talla": "L"}, 280)]),
            ("Ponchos", "Poncho impermeable andino", 380, "poncho,impermeable", None),
            ("Chalinas", "Chalina de alpaca", 95, "chalina,alpaca,accesorio",
             [("Gris", {"color": "Gris"}, 95), ("Beige", {"color": "Beige"}, 95),
              ("Vino", {"color": "Vino"}, 95)]),
            ("Chalinas", "Chalina de baby alpaca", 160, "chalina,baby-alpaca", None),
            ("Chalinas", "Bufanda tejida a crochet", 70, "bufanda,crochet", None),
            ("Chompas", "Chompa jacquard andina", 290, "chompa,jacquard",
             [("S", {"talla": "S"}, 290), ("M", {"talla": "M"}, 300),
              ("L", {"talla": "L"}, 310)]),
            ("Chompas", "Chompa de alpaca cuello alto", 340, "chompa,alpaca",
             [("S", {"talla": "S"}, 340), ("M", {"talla": "M"}, 350),
              ("L", {"talla": "L"}, 360)]),
            ("Chompas", "Cardigan de lana natural", 300, "cardigan,lana", None),
            ("Gorros", "Gorro chullo con orejeras", 55, "gorro,chullo", None),
            ("Gorros", "Gorro de alpaca con pompon", 65, "gorro,alpaca", None),
            ("Gorros", "Vincha tejida andina", 35, "vincha,accesorio", None),
            ("Accesorios", "Guantes de lana tejidos", 45, "guantes,lana",
             [("S/M", {"talla": "S/M"}, 45), ("L/XL", {"talla": "L/XL"}, 45)]),
            ("Accesorios", "Medias de alpaca gruesas", 40, "medias,alpaca", None),
            ("Bolsos", "Bolso tejido a mano", 130, "bolso,tejido", None),
            ("Bolsos", "Mochila andina de aguayo", 180, "mochila,aguayo", None),
            ("Bolsos", "Monedero de aguayo", 35, "monedero,aguayo", None),
            ("Hogar", "Tapiz decorativo de pared", 260, "tapiz,decoracion", None),
            ("Hogar", "Camino de mesa andino", 140, "mantel,hogar", None),
        ],
    ),
    dict(
        slug="sabores-de-bolivia", nombre="Sabores de Bolivia", color="#27AE60",
        owner="empresa2@kantu.bo", ciudad="Cochabamba",
        direccion="Av. America 1500", telefono="+591 72345678",
        descripcion=("Cafe de altura, chocolate de cacao boliviano, infusiones y "
                     "snacks andinos desde Cochabamba."),
        desc_tpl="{n}. Producto boliviano seleccionado, ideal para regalo o consumo diario.",
        prefix="SDB",
        productos=[
            ("Cafes", "Cafe de altura Yungas 250g", 55, "cafe,yungas,arabica",
             [("Molido", {"presentacion": "Molido"}, 55),
              ("Grano", {"presentacion": "Grano"}, 55)]),
            ("Cafes", "Cafe organico Caranavi 500g", 110, "cafe,organico",
             [("Molido", {"presentacion": "Molido"}, 110),
              ("Grano", {"presentacion": "Grano"}, 110)]),
            ("Cafes", "Cafe en grano espresso 1kg", 190, "cafe,espresso", None),
            ("Cafes", "Cafe descafeinado 250g", 60, "cafe,descafeinado", None),
            ("Cafes", "Capsulas de cafe compatibles x10", 45, "cafe,capsulas", None),
            ("Cafes", "Cafe soluble frasco 170g", 50, "cafe,soluble", None),
            ("Chocolates", "Chocolate 70% cacao boliviano", 28, "chocolate,cacao", None),
            ("Chocolates", "Chocolate con leche y quinua", 26, "chocolate,quinua", None),
            ("Chocolates", "Chocolate 100% cacao Alto Beni", 34, "chocolate,puro", None),
            ("Chocolates", "Cocoa en polvo 200g", 32, "cocoa,reposteria", None),
            ("Chocolates", "Bombones surtidos caja x12", 55, "bombones,regalo", None),
            ("Infusiones", "Mate de coca en bolsitas x25", 18, "mate,coca,infusion", None),
            ("Infusiones", "Te de manzanilla andina x25", 16, "te,manzanilla", None),
            ("Infusiones", "Infusion de muna 40g", 22, "muna,digestivo", None),
            ("Infusiones", "Anis de campo 40g", 15, "anis,infusion", None),
            ("Snacks", "Quinua pop con miel 80g", 15, "quinua,snack", None),
            ("Snacks", "Barras de amaranto x6", 24, "amaranto,barra", None),
            ("Snacks", "Mani tostado con sal 200g", 18, "mani,snack", None),
            ("Snacks", "Habas fritas picantes 150g", 16, "habas,picante", None),
            ("Snacks", "Chips de camote 120g", 20, "camote,chips", None),
            ("Snacks", "Tostado de maiz willkaparu 250g", 17, "maiz,tostado", None),
            ("Despensa", "Miel de abeja pura 500g", 45, "miel,natural", None),
            ("Despensa", "Azucar de cana integral 1kg", 22, "azucar,cana", None),
            ("Despensa", "Sal rosada de Uyuni 250g", 18, "sal,uyuni", None),
            ("Despensa", "Aji amarillo molido 100g", 15, "aji,condimento", None),
            ("Despensa", "Quinua real blanca 1kg", 48, "quinua,grano", None),
            ("Despensa", "Chia organica 250g", 28, "chia,superalimento", None),
            ("Despensa", "Cañahua en hojuelas 400g", 30, "canahua,cereal", None),
        ],
    ),
    dict(
        slug="tecno-oriente", nombre="Tecno Oriente", color="#2E86C1",
        owner="empresa3@kantu.bo", ciudad="Santa Cruz",
        direccion="Av. Monsenor Rivero 300", telefono="+591 73456789",
        descripcion=("Accesorios, audio, cargadores y gadgets para tu celular. "
                     "Tienda crucena con envios a todo el pais."),
        desc_tpl="{n}. Accesorio con garantia de 3 meses y envios a todo el pais.",
        prefix="TEC",
        productos=[
            ("Fundas", "Funda de silicona para celular", 45, "funda,silicona",
             [("Negro", {"color": "Negro"}, 45), ("Azul", {"color": "Azul"}, 45),
              ("Transparente", {"color": "Transparente"}, 45)]),
            ("Fundas", "Funda transparente antishock", 55, "funda,antishock", None),
            ("Fundas", "Funda tipo cartera con tarjetero", 75, "funda,cartera", None),
            ("Proteccion", "Vidrio templado 9H", 25, "vidrio,proteccion",
             [("Pack x1", {"pack": "1"}, 25), ("Pack x2", {"pack": "2"}, 40)]),
            ("Proteccion", "Protector de camara de vidrio", 20, "camara,proteccion", None),
            ("Audio", "Audifonos inalambricos TWS", 220, "audifonos,bluetooth,tws", None),
            ("Audio", "Audifonos con cable y microfono", 45, "audifonos,cable", None),
            ("Audio", "Audifonos deportivos con gancho", 120, "audifonos,deporte", None),
            ("Audio", "Parlante bluetooth portatil", 180, "parlante,bluetooth", None),
            ("Audio", "Parlante bluetooth resistente al agua", 260, "parlante,ipx7", None),
            ("Audio", "Microfono lavalier para celular", 90, "microfono,creador", None),
            ("Energia", "Cargador rapido USB-C 20W", 60, "cargador,usbc", None),
            ("Energia", "Cargador de auto doble puerto", 55, "cargador,auto", None),
            ("Energia", "Power bank 10000mAh", 130, "powerbank,bateria", None),
            ("Energia", "Power bank 20000mAh carga rapida", 210, "powerbank,pd", None),
            ("Energia", "Cargador inalambrico 15W", 95, "cargador,qi", None),
            ("Cables", "Cable USB-C a USB-C 1m", 25, "cable,usbc",
             [("1 metro", {"largo": "1m"}, 25), ("2 metros", {"largo": "2m"}, 35)]),
            ("Cables", "Cable Lightning trenzado 2m", 40, "cable,lightning", None),
            ("Cables", "Cable USB-C a HDMI 4K", 85, "cable,hdmi", None),
            ("Almacenamiento", "Memoria USB 64GB", 55, "usb,almacenamiento", None),
            ("Almacenamiento", "MicroSD 128GB clase 10", 95, "microsd,almacenamiento", None),
            ("Almacenamiento", "Hub USB-C 6 en 1", 160, "hub,usbc", None),
            ("Wearables", "Smartwatch deportivo", 320, "smartwatch,fitness",
             [("Negro", {"color": "Negro"}, 320), ("Plata", {"color": "Plata"}, 330)]),
            ("Wearables", "Banda de actividad fisica", 150, "smartband,fitness", None),
            ("Accesorios", "Soporte de celular para auto", 60, "soporte,auto", None),
            ("Accesorios", "Aro de luz LED 10 pulgadas", 110, "aro-luz,creador", None),
            ("Accesorios", "Tripode flexible para celular", 45, "tripode,foto", None),
            ("Gaming", "Gamepad bluetooth", 140, "gamepad,gaming", None),
            ("Gaming", "Mouse inalambrico", 70, "mouse,pc", None),
            ("Gaming", "Teclado bluetooth compacto", 160, "teclado,pc", None),
            ("Hogar", "Foco inteligente WiFi RGB", 65, "foco,smart-home", None),
            ("Hogar", "Enchufe inteligente WiFi", 70, "enchufe,smart-home", None),
        ],
    ),
    dict(
        slug="ceramica-tiwanaku", nombre="Ceramica Tiwanaku", color="#A04000",
        owner="empresa4@kantu.bo", ciudad="El Alto",
        direccion="Ceja de El Alto, Calle 2", telefono="+591 74567890",
        descripcion=("Vajilla, macetas, iluminacion y piezas decorativas de "
                     "ceramica trabajadas y pintadas a mano en El Alto."),
        desc_tpl="{n}. Pieza de ceramica trabajada y pintada a mano en {c}.",
        prefix="CTW",
        productos=[
            ("Vajilla", "Juego de tazas andinas x4", 140, "tazas,vajilla", None),
            ("Vajilla", "Juego de platos esmaltados x6", 260, "platos,vajilla", None),
            ("Vajilla", "Bowl de ceramica rustica", 45, "bowl,vajilla",
             [("Chico", {"tamano": "Chico"}, 45), ("Grande", {"tamano": "Grande"}, 65)]),
            ("Vajilla", "Ensaladera grande pintada", 120, "ensaladera,vajilla", None),
            ("Vajilla", "Fuente ovalada para horno", 110, "fuente,horno", None),
            ("Tazas y jarros", "Jarra de agua 1.5L", 95, "jarra,mesa", None),
            ("Tazas y jarros", "Set de jarro y vasos x4", 150, "jarro,vasos", None),
            ("Tazas y jarros", "Taza mug artesanal", 40, "taza,mug",
             [("Azul", {"color": "Azul"}, 40), ("Verde", {"color": "Verde"}, 40),
              ("Terracota", {"color": "Terracota"}, 40)]),
            ("Tazas y jarros", "Taza espresso x2", 55, "taza,espresso", None),
            ("Tazas y jarros", "Chop cervecero de ceramica", 60, "chop,cerveza", None),
            ("Decoracion", "Plato decorativo Tiwanaku", 85, "plato,decoracion",
             [("Mediano", {"tamano": "Mediano"}, 85), ("Grande", {"tamano": "Grande"}, 130)]),
            ("Decoracion", "Cuadro ceramico Puerta del Sol", 190, "cuadro,tiwanaku", None),
            ("Decoracion", "Figura de chakana", 70, "chakana,decoracion", None),
            ("Decoracion", "Portavelas de ceramica x3", 60, "portavelas,decoracion", None),
            ("Decoracion", "Campana de viento de ceramica", 55, "campana,jardin", None),
            ("Floreros", "Florero de ceramica esmaltada", 95, "florero,decoracion", None),
            ("Floreros", "Florero alto minimalista", 120, "florero,minimalista", None),
            ("Floreros", "Set de 3 mini floreros", 80, "florero,set", None),
            ("Macetas", "Maceta de barro pintada a mano", 35, "maceta,barro",
             [("Chica", {"tamano": "Chica"}, 35), ("Mediana", {"tamano": "Mediana"}, 55),
              ("Grande", {"tamano": "Grande"}, 80)]),
            ("Macetas", "Maceta colgante trenzada", 65, "maceta,colgante", None),
            ("Macetas", "Set de macetas pequenas x3", 90, "maceta,set", None),
            ("Macetas", "Maceta grande para exterior", 130, "maceta,exterior", None),
            ("Iluminacion", "Lampara de mesa de ceramica", 220, "lampara,iluminacion", None),
            ("Iluminacion", "Aplique de pared artesanal", 140, "aplique,iluminacion", None),
            ("Utensilios", "Individuales de ceramica x4", 70, "individuales,mesa", None),
            ("Utensilios", "Salero y pimentero", 45, "salero,mesa", None),
            ("Utensilios", "Aceitera de ceramica", 50, "aceitera,cocina", None),
            ("Utensilios", "Mortero de piedra volcanica", 85, "mortero,cocina", None),
            ("Aromas", "Difusor de aromas de ceramica", 75, "difusor,aromas", None),
            ("Aromas", "Quemador de incienso artesanal", 40, "incienso,aromas", None),
        ],
    ),
]

STOCK_CYCLE = [15, 40, 8, 0, 25, 12, 60, 5, 3, 30, 18, 0, 22, 7, 45, 10, 33, 4, 27, 50]

TIENDA_SLUGS = "(" + ", ".join(q(s["slug"]) for s in STORES) + ")"


def values_block(rows, indent="    "):
    return ",\n".join(indent + r for r in rows)


def main():
    out = io.StringIO()
    w = out.write

    w("-- ============================================================================\n")
    w("-- Kantu Market - Poblacion de datos demo (catalogo grande para demostracion)\n")
    w("-- ============================================================================\n")
    w("--\n")
    w("-- GENERADO automaticamente. No editar a mano: cambiar el generador y regenerar.\n")
    w("--\n")
    w("-- Crea 4 empresas + 4 tiendas + clientes, con categorias, productos (15+ por\n")
    w("-- tienda) y variantes. No depende de Cloudinary (imagenes = picsum.photos).\n")
    w("--\n")
    w("-- Requisitos: migraciones aplicadas (python manage.py migrate). Los roles\n")
    w("-- semilla ya existen por usuarios/0002_roles_semilla.\n")
    w("--\n")
    w("-- Ejecucion (ajustar segun tu .env):\n")
    w("--   psql -h localhost -U postgres -d kantu_market -f seed_empresas.sql\n")
    w("--\n")
    w("-- Re-ejecutable: primero hace un reset del catalogo de las 4 tiendas demo\n")
    w("-- (paso 0) y luego re-inserta todo. Usuarios y tiendas se mantienen por\n")
    w("-- clave natural (email / slug). El archivo es 100% ASCII a proposito.\n")
    w("--\n")
    w("-- Credenciales de todos los usuarios demo:  Password123!\n")
    for s in STORES:
        w("--   {:<18} -> {:<22} ({})\n".format(s["owner"], s["nombre"], s["slug"]))
    w("--   " + ", ".join(c[2] for c in CLIENTES) + "\n")
    w("-- ============================================================================\n\n")

    w("SET client_encoding TO 'UTF8';\n\n")
    w("BEGIN;\n\n")

    # 0. Reset del catalogo demo
    dm = TIENDA_SLUGS
    prod_ids = ("SELECT p.id FROM producto p JOIN tienda t ON t.id = p.tienda_id\n"
                "     WHERE t.slug IN %s" % dm)
    var_ids = ("SELECT v.id FROM variante v\n"
               "     JOIN producto p ON p.id = v.producto_id\n"
               "     JOIN tienda t ON t.id = p.tienda_id\n"
               "     WHERE t.slug IN %s" % dm)
    w("-- 0. Reset determinista del catalogo demo.\n")
    w("--    Solo toca las 4 tiendas demo; NO borra usuarios ni las tiendas.\n")
    w("--    Si algun DELETE falla por FK es que hay datos reales (pedidos, resenas,\n")
    w("--    eventos IA) sobre el catalogo demo: revisar antes de continuar.\n")
    w("DELETE FROM item_carrito WHERE variante_id IN (\n     %s);\n" % var_ids)
    w("DELETE FROM item_pedido  WHERE variante_id IN (\n     %s);\n" % var_ids)
    w("DELETE FROM variante WHERE producto_id IN (\n     %s);\n" % prod_ids)
    w("DELETE FROM producto WHERE tienda_id IN (SELECT id FROM tienda WHERE slug IN %s);\n" % dm)
    w("DELETE FROM categoria WHERE tienda_id IN (SELECT id FROM tienda WHERE slug IN %s);\n" % dm)
    w("DELETE FROM direccion_tienda WHERE tienda_id IN (SELECT id FROM tienda WHERE slug IN %s);\n\n" % dm)

    # 1. Usuarios
    w("-- 1. Usuarios (4 empresas + %d clientes). Hash = 'Password123!'.\n" % len(CLIENTES))
    w("INSERT INTO usuario\n")
    w("    (password, is_superuser, first_name, last_name, is_staff, is_active,\n")
    w("     date_joined, email, fecha_registro, activo, rol_id)\n")
    w("SELECT\n")
    w("    '%s',\n" % PASSWORD_HASH)
    w("    false, d.first_name, d.last_name, false, true,\n")
    w("    now(), d.email, now(), true,\n")
    w("    (SELECT id FROM rol WHERE nombre = d.rol)\n")
    rows = []
    for fn, ln, em in EMPRESAS:
        rows.append("(%s, %s, %s, 'empresa')" % (q(fn), q(ln), q(em)))
    for fn, ln, em in CLIENTES:
        rows.append("(%s, %s, %s, 'cliente')" % (q(fn), q(ln), q(em)))
    w("FROM (VALUES\n")
    w(values_block(rows))
    w("\n) AS d(first_name, last_name, email, rol)\n")
    w("WHERE NOT EXISTS (SELECT 1 FROM usuario u WHERE u.email = d.email);\n\n")

    # 2. Tiendas
    w("-- 2. Tiendas (una por empresa)\n")
    w("INSERT INTO tienda\n")
    w("    (nombre, slug, logo_url, color_primario, descripcion, fecha_creacion,\n")
    w("     activa, propietario_id)\n")
    w("SELECT\n")
    w("    d.nombre, d.slug, '', d.color, d.descripcion, now(), true,\n")
    w("    (SELECT id FROM usuario WHERE email = d.owner_email)\n")
    rows = []
    for s in STORES:
        rows.append("(%s, %s, %s,\n     %s,\n     %s)" % (
            q(s["nombre"]), q(s["slug"]), q(s["color"]),
            q(s["descripcion"]), q(s["owner"])))
    w("FROM (VALUES\n")
    w(values_block(rows))
    w("\n) AS d(nombre, slug, color, descripcion, owner_email)\n")
    w("WHERE NOT EXISTS (SELECT 1 FROM tienda t WHERE t.slug = d.slug);\n\n")

    # 3. usuario_tienda
    w("-- 3. Vinculo propietario <-> tienda\n")
    w("INSERT INTO usuario_tienda (rol_interno, fecha_asignacion, tienda_id, usuario_id)\n")
    w("SELECT 'propietario', now(), t.id, t.propietario_id\n")
    w("FROM tienda t\n")
    w("WHERE t.slug IN %s\n" % TIENDA_SLUGS)
    w("  AND NOT EXISTS (\n")
    w("      SELECT 1 FROM usuario_tienda ut\n")
    w("      WHERE ut.tienda_id = t.id AND ut.usuario_id = t.propietario_id\n")
    w("  );\n\n")

    # 4. direccion_tienda
    w("-- 4. Direcciones de tienda\n")
    w("INSERT INTO direccion_tienda (direccion, ciudad, telefono, tienda_id)\n")
    w("SELECT d.direccion, d.ciudad, d.telefono,\n")
    w("       (SELECT id FROM tienda WHERE slug = d.slug)\n")
    rows = []
    for s in STORES:
        rows.append("(%s, %s, %s, %s)" % (
            q(s["slug"]), q(s["direccion"]), q(s["ciudad"]), q(s["telefono"])))
    w("FROM (VALUES\n")
    w(values_block(rows))
    w("\n) AS d(slug, direccion, ciudad, telefono)\n")
    w("WHERE NOT EXISTS (\n")
    w("    SELECT 1 FROM direccion_tienda dt\n")
    w("    WHERE dt.tienda_id = (SELECT id FROM tienda WHERE slug = d.slug)\n")
    w(");\n\n")

    # 5. categorias
    w("-- 5. Categorias (por tienda)\n")
    w("INSERT INTO categoria (nombre, categoria_padre_id, tienda_id)\n")
    w("SELECT d.nombre, NULL, (SELECT id FROM tienda WHERE slug = d.slug)\n")
    rows = []
    for s in STORES:
        cats = []
        for p in s["productos"]:
            if p[0] not in cats:
                cats.append(p[0])
        for c in cats:
            rows.append("(%s, %s)" % (q(s["slug"]), q(c)))
    w("FROM (VALUES\n")
    w(values_block(rows))
    w("\n) AS d(slug, nombre)\n")
    w("WHERE NOT EXISTS (\n")
    w("    SELECT 1 FROM categoria c\n")
    w("    WHERE c.tienda_id = (SELECT id FROM tienda WHERE slug = d.slug)\n")
    w("      AND c.nombre = d.nombre\n")
    w(");\n\n")

    # Preparar productos + variantes con SKUs deterministas
    prod_rows = []
    var_rows = []
    vi = 0
    for s in STORES:
        seen_slugs = {}
        for idx, (cat, nombre, precio, tags, variantes) in enumerate(s["productos"], start=1):
            pslug = slugify(nombre)
            if pslug in seen_slugs:
                seen_slugs[pslug] += 1
                pslug = "%s-%d" % (pslug, seen_slugs[pslug])
            else:
                seen_slugs[pslug] = 1
            desc = s["desc_tpl"].format(n=nombre, c=s["ciudad"])
            prod_rows.append("(%s, %s, %s,\n     %s,\n     %s,\n     %s)" % (
                q(s["slug"]), q(cat), q(nombre), q(pslug), q(desc), q(tags)))
            code = "%s-%03d" % (s["prefix"], idx)
            vlist = variantes if variantes else [("Unica", {}, precio)]
            for j, (sufijo, attrs, vprecio) in enumerate(vlist, start=1):
                vi += 1
                stock = STOCK_CYCLE[vi % len(STOCK_CYCLE)]
                stock_min = 5 if stock >= 10 else 3
                oferta = "NULL"
                if vi % 5 == 3:
                    oferta = "%.2f" % round(vprecio * 0.85, 2)
                sku = code if len(vlist) == 1 else "%s-%d" % (code, j)
                import json
                attrs_json = json.dumps(attrs, ensure_ascii=True)
                var_rows.append("(%s, %s, %s, %s, %.2f, %s, %d, %d, %s)" % (
                    q(s["slug"]), q(pslug), q(sufijo), q(sku),
                    float(vprecio), oferta, stock, stock_min, q(attrs_json)))

    # 6. productos
    w("-- 6. Productos (imagenes: placeholder de picsum.photos)\n")
    w("INSERT INTO producto\n")
    w("    (nombre, descripcion, activo, categoria_id, tienda_id, slug,\n")
    w("     etiquetas, imagenes, creado, actualizado)\n")
    w("SELECT\n")
    w("    d.nombre, d.descripcion, true,\n")
    w("    (SELECT c.id FROM categoria c\n")
    w("       WHERE c.tienda_id = (SELECT id FROM tienda WHERE slug = d.slug)\n")
    w("         AND c.nombre = d.categoria\n")
    w("       LIMIT 1),\n")
    w("    (SELECT id FROM tienda WHERE slug = d.slug),\n")
    w("    d.pslug,\n")
    w("    string_to_array(d.etiquetas, ',')::varchar(50)[],\n")
    w("    ('[{\"url\": \"https://picsum.photos/seed/' || d.pslug ||\n")
    w("        '/600/600\", \"public_id\": \"seed/' || d.pslug || '\"}]')::jsonb,\n")
    w("    now(), now()\n")
    w("FROM (VALUES\n")
    w(values_block(prod_rows))
    w("\n) AS d(slug, categoria, nombre, pslug, descripcion, etiquetas)\n")
    w("WHERE NOT EXISTS (\n")
    w("    SELECT 1 FROM producto p\n")
    w("    WHERE p.tienda_id = (SELECT id FROM tienda WHERE slug = d.slug)\n")
    w("      AND p.slug = d.pslug\n")
    w(");\n\n")

    # 7. variantes
    w("-- 7. Variantes (incluye precio_oferta, multi-variante y stock 0 / bajo)\n")
    w("INSERT INTO variante\n")
    w("    (nombre, sku, producto_id, precio, precio_oferta, stock, stock_minimo,\n")
    w("     atributos, activa)\n")
    w("SELECT\n")
    w("    d.vnombre, d.sku,\n")
    w("    (SELECT p.id FROM producto p\n")
    w("       WHERE p.tienda_id = (SELECT id FROM tienda WHERE slug = d.slug)\n")
    w("         AND p.slug = d.pslug\n")
    w("       LIMIT 1),\n")
    w("    d.precio::numeric, d.precio_oferta::numeric, d.stock, d.stock_minimo,\n")
    w("    d.atributos::jsonb, true\n")
    w("FROM (VALUES\n")
    w(values_block(var_rows))
    w("\n) AS d(slug, pslug, vnombre, sku, precio, precio_oferta, stock, stock_minimo, atributos)\n")
    w("WHERE NOT EXISTS (\n")
    w("    SELECT 1 FROM variante v\n")
    w("    WHERE v.producto_id = (\n")
    w("              SELECT p.id FROM producto p\n")
    w("              WHERE p.tienda_id = (SELECT id FROM tienda WHERE slug = d.slug)\n")
    w("                AND p.slug = d.pslug\n")
    w("              LIMIT 1)\n")
    w("      AND v.sku = d.sku\n")
    w(");\n\n")

    # 8. resumen
    w("-- 8. Resumen\n")
    w("SELECT\n")
    w("    (SELECT count(*) FROM usuario WHERE email IN (%s)) AS empresas,\n"
      % ", ".join(q(e[2]) for e in EMPRESAS))
    w("    (SELECT count(*) FROM tienda WHERE slug IN %s) AS tiendas,\n" % TIENDA_SLUGS)
    w("    (SELECT count(*) FROM categoria c JOIN tienda t ON t.id = c.tienda_id\n")
    w("        WHERE t.slug IN %s) AS categorias,\n" % TIENDA_SLUGS)
    w("    (SELECT count(*) FROM producto p JOIN tienda t ON t.id = p.tienda_id\n")
    w("        WHERE t.slug IN %s) AS productos,\n" % TIENDA_SLUGS)
    w("    (SELECT count(*) FROM variante v\n")
    w("        JOIN producto p ON p.id = v.producto_id\n")
    w("        JOIN tienda t ON t.id = p.tienda_id\n")
    w("        WHERE t.slug IN %s) AS variantes;\n\n" % TIENDA_SLUGS)

    w("COMMIT;\n")

    data = out.getvalue()
    with open(OUT, "w", encoding="ascii", newline="\n") as fh:
        fh.write(data)

    n_prod = len(prod_rows)
    n_var = len(var_rows)
    print("Escrito %s" % OUT)
    print("productos: %d, variantes: %d" % (n_prod, n_var))
    for s in STORES:
        print("  %-22s %d productos" % (s["nombre"], len(s["productos"])))


if __name__ == "__main__":
    main()
