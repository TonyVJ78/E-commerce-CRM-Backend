-- ============================================================================
-- Kantu Market - Poblacion de datos demo: 4 empresas con catalogo
-- ============================================================================
--
-- Crea 4 usuarios con rol "empresa", 4 tiendas (una por empresa), 3 clientes,
-- categorias, productos y variantes de ejemplo. Sirve para tener datos
-- consistentes entre companeros de equipo sin depender de Cloudinary
-- (a diferencia de seed_demo.py).
--
-- Requisitos previos:
--   * Migraciones aplicadas (python manage.py migrate). Los roles semilla
--     'administrador' / 'empresa' / 'cliente' ya existen por la migracion
--     usuarios/0002_roles_semilla.
--
-- Como ejecutarlo (ajustar DB/usuario segun tu .env):
--   psql -h localhost -U postgres -d kantu_market -f seed_empresas.sql
--
-- Es idempotente: se puede correr varias veces, no duplica filas
-- (usa "WHERE NOT EXISTS" contra las claves naturales: email / slug / sku).
--
-- Credenciales de todos los usuarios demo:  Password123!
--   empresa1@kantu.bo  -> Textiles Los Andes   (textiles-los-andes)
--   empresa2@kantu.bo  -> Sabores de Bolivia   (sabores-de-bolivia)
--   empresa3@kantu.bo  -> Tecno Oriente        (tecno-oriente)
--   empresa4@kantu.bo  -> Ceramica Tiwanaku    (ceramica-tiwanaku)
--   cliente1@kantu.bo, cliente2@kantu.bo, cliente3@kantu.bo
-- ============================================================================

-- El archivo es 100% ASCII a proposito (sin tildes ni enie) para que no
-- dependa del client_encoding de psql en Windows. Igual lo forzamos a UTF8.
SET client_encoding TO 'UTF8';

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. Usuarios (4 empresas + 3 clientes)
--    El hash corresponde a la contrasena "Password123!" (pbkdf2_sha256).
-- ----------------------------------------------------------------------------
INSERT INTO usuario
    (password, is_superuser, first_name, last_name, is_staff, is_active,
     date_joined, email, fecha_registro, activo, rol_id)
SELECT
    'pbkdf2_sha256$870000$KcLpbH6MM9wGs6RPDjxWbD$7p/ETMzaYAKjYYsXm5F6O4vZpT7fEvtURZSnr20DT6U=',
    false, d.first_name, d.last_name, false, true,
    now(), d.email, now(), true,
    (SELECT id FROM rol WHERE nombre = d.rol)
FROM (VALUES
    ('Maria',  'Condori',   'empresa1@kantu.bo', 'empresa'),
    ('Jorge',  'Vargas',    'empresa2@kantu.bo', 'empresa'),
    ('Rosa',   'Flores',    'empresa3@kantu.bo', 'empresa'),
    ('David',  'Mamani',    'empresa4@kantu.bo', 'empresa'),
    ('Lucia',  'Rojas',     'cliente1@kantu.bo', 'cliente'),
    ('Pedro',  'Gutierrez', 'cliente2@kantu.bo', 'cliente'),
    ('Carla',  'Ticona',    'cliente3@kantu.bo', 'cliente')
) AS d(first_name, last_name, email, rol)
WHERE NOT EXISTS (SELECT 1 FROM usuario u WHERE u.email = d.email);

-- ----------------------------------------------------------------------------
-- 2. Tiendas (una por empresa)
-- ----------------------------------------------------------------------------
INSERT INTO tienda
    (nombre, slug, logo_url, color_primario, descripcion, fecha_creacion,
     activa, propietario_id)
SELECT
    d.nombre, d.slug, '', d.color, d.descripcion, now(), true,
    (SELECT id FROM usuario WHERE email = d.owner_email)
FROM (VALUES
    ('Textiles Los Andes', 'textiles-los-andes', '#C8102E',
     'Aguayos, ponchos y chalinas tejidos a mano en La Paz con lana de alpaca y oveja.',
     'empresa1@kantu.bo'),
    ('Sabores de Bolivia', 'sabores-de-bolivia', '#27AE60',
     'Cafe de altura, chocolate de cacao boliviano y snacks andinos desde Cochabamba.',
     'empresa2@kantu.bo'),
    ('Tecno Oriente', 'tecno-oriente', '#2E86C1',
     'Accesorios, audio y cargadores para tu celular. Tienda crucena con envios a todo el pais.',
     'empresa3@kantu.bo'),
    ('Ceramica Tiwanaku', 'ceramica-tiwanaku', '#A04000',
     'Vajilla, macetas y piezas decorativas de ceramica pintadas a mano en El Alto.',
     'empresa4@kantu.bo')
) AS d(nombre, slug, color, descripcion, owner_email)
WHERE NOT EXISTS (SELECT 1 FROM tienda t WHERE t.slug = d.slug);

-- ----------------------------------------------------------------------------
-- 3. Vinculo propietario <-> tienda en usuario_tienda
-- ----------------------------------------------------------------------------
INSERT INTO usuario_tienda (rol_interno, fecha_asignacion, tienda_id, usuario_id)
SELECT 'propietario', now(), t.id, t.propietario_id
FROM tienda t
WHERE t.slug IN ('textiles-los-andes', 'sabores-de-bolivia', 'tecno-oriente', 'ceramica-tiwanaku')
  AND NOT EXISTS (
      SELECT 1 FROM usuario_tienda ut
      WHERE ut.tienda_id = t.id AND ut.usuario_id = t.propietario_id
  );

-- ----------------------------------------------------------------------------
-- 4. Direcciones de tienda
-- ----------------------------------------------------------------------------
INSERT INTO direccion_tienda (direccion, ciudad, telefono, tienda_id)
SELECT d.direccion, d.ciudad, d.telefono,
       (SELECT id FROM tienda WHERE slug = d.slug)
FROM (VALUES
    ('textiles-los-andes', 'Calle Sagarnaga 245', 'La Paz',     '+591 71234567'),
    ('sabores-de-bolivia', 'Av. America 1500',    'Cochabamba', '+591 72345678'),
    ('tecno-oriente',      'Av. Monsenor Rivero 300', 'Santa Cruz', '+591 73456789'),
    ('ceramica-tiwanaku',  'Ceja de El Alto, Calle 2', 'El Alto', '+591 74567890')
) AS d(slug, direccion, ciudad, telefono)
WHERE NOT EXISTS (
    SELECT 1 FROM direccion_tienda dt
    WHERE dt.tienda_id = (SELECT id FROM tienda WHERE slug = d.slug)
);

-- ----------------------------------------------------------------------------
-- 5. Categorias (por tienda)
-- ----------------------------------------------------------------------------
INSERT INTO categoria (nombre, categoria_padre_id, tienda_id)
SELECT d.nombre, NULL, (SELECT id FROM tienda WHERE slug = d.slug)
FROM (VALUES
    ('textiles-los-andes', 'Aguayos'),
    ('textiles-los-andes', 'Ponchos'),
    ('textiles-los-andes', 'Chalinas'),
    ('sabores-de-bolivia', 'Cafes'),
    ('sabores-de-bolivia', 'Chocolates'),
    ('sabores-de-bolivia', 'Snacks'),
    ('tecno-oriente',      'Accesorios'),
    ('tecno-oriente',      'Audio'),
    ('tecno-oriente',      'Cargadores'),
    ('ceramica-tiwanaku',  'Vajilla'),
    ('ceramica-tiwanaku',  'Decoracion'),
    ('ceramica-tiwanaku',  'Macetas')
) AS d(slug, nombre)
WHERE NOT EXISTS (
    SELECT 1 FROM categoria c
    WHERE c.tienda_id = (SELECT id FROM tienda WHERE slug = d.slug)
      AND c.nombre = d.nombre
);

-- ----------------------------------------------------------------------------
-- 6. Productos
--    imagenes: placeholder de picsum.photos (no requiere Cloudinary).
-- ----------------------------------------------------------------------------
INSERT INTO producto
    (nombre, descripcion, activo, categoria_id, tienda_id, slug,
     etiquetas, imagenes, creado, actualizado)
SELECT
    d.nombre, d.descripcion, true,
    (SELECT c.id FROM categoria c
       WHERE c.tienda_id = (SELECT id FROM tienda WHERE slug = d.slug)
         AND c.nombre = d.categoria
       LIMIT 1),
    (SELECT id FROM tienda WHERE slug = d.slug),
    d.pslug,
    string_to_array(d.etiquetas, ',')::varchar(50)[],
    ('[{"url": "https://picsum.photos/seed/' || d.pslug ||
        '/600/600", "public_id": "seed/' || d.pslug || '"}]')::jsonb,
    now(), now()
FROM (VALUES
    -- Textiles Los Andes
    ('textiles-los-andes', 'Aguayos',  'Aguayo tradicional paceno',
        'aguayo-tradicional-paceno',
        'Aguayo tejido a mano con lana de oveja tenida con tintes naturales. Ideal para cargar o decorar.',
        'aguayo,tejido,artesanal'),
    ('textiles-los-andes', 'Aguayos',  'Aguayo grande multicolor',
        'aguayo-grande-multicolor',
        'Aguayo de gran formato con franjas multicolor, tejido en telar tradicional.',
        'aguayo,telar,artesanal'),
    ('textiles-los-andes', 'Ponchos',  'Poncho de alpaca cafe',
        'poncho-alpaca-cafe',
        'Poncho abrigado 100% fibra de alpaca en tono cafe natural.',
        'poncho,alpaca,abrigo'),
    ('textiles-los-andes', 'Chalinas', 'Chalina de alpaca',
        'chalina-de-alpaca',
        'Chalina suave de fibra de alpaca, liviana y calida.',
        'chalina,alpaca,accesorio'),
    -- Sabores de Bolivia
    ('sabores-de-bolivia', 'Cafes',      'Cafe de altura Yungas 250g',
        'cafe-altura-yungas-250g',
        'Cafe arabica cultivado en los Yungas de La Paz. Tueste medio, notas a chocolate y panela.',
        'cafe,yungas,arabica'),
    ('sabores-de-bolivia', 'Cafes',      'Cafe organico Caranavi 500g',
        'cafe-organico-caranavi-500g',
        'Cafe organico certificado de Caranavi. Tueste medio-oscuro, cuerpo intenso.',
        'cafe,organico,caranavi'),
    ('sabores-de-bolivia', 'Chocolates', 'Chocolate 70% cacao boliviano',
        'chocolate-70-cacao-boliviano',
        'Barra de chocolate amargo 70% con cacao del Alto Beni.',
        'chocolate,cacao,altobeni'),
    ('sabores-de-bolivia', 'Snacks',     'Quinua pop con miel',
        'quinua-pop-con-miel',
        'Quinua real inflada y cubierta con miel de abeja. Snack liviano sin gluten.',
        'quinua,snack,singluten'),
    -- Tecno Oriente
    ('tecno-oriente', 'Accesorios', 'Funda de silicona para celular',
        'funda-silicona-celular',
        'Funda flexible de silicona con bordes reforzados. Varios colores.',
        'funda,silicona,proteccion'),
    ('tecno-oriente', 'Audio',      'Audifonos inalambricos TWS',
        'audifonos-inalambricos-tws',
        'Audifonos bluetooth 5.3 con estuche de carga y microfono. Autonomia 24h con estuche.',
        'audifonos,bluetooth,tws'),
    ('tecno-oriente', 'Audio',      'Parlante bluetooth portatil',
        'parlante-bluetooth-portatil',
        'Parlante compacto resistente a salpicaduras, 10W, hasta 8h de reproduccion.',
        'parlante,bluetooth,portatil'),
    ('tecno-oriente', 'Cargadores', 'Cargador rapido USB-C 20W',
        'cargador-rapido-usbc-20w',
        'Cargador de pared con Power Delivery 20W y cable USB-C incluido.',
        'cargador,usbc,carga-rapida'),
    -- Ceramica Tiwanaku
    ('ceramica-tiwanaku', 'Vajilla',    'Juego de tazas andinas x4',
        'juego-tazas-andinas-x4',
        'Set de 4 tazas de ceramica esmaltada con grecas andinas. Aptas para microondas.',
        'tazas,ceramica,vajilla'),
    ('ceramica-tiwanaku', 'Decoracion', 'Plato decorativo Tiwanaku',
        'plato-decorativo-tiwanaku',
        'Plato de pared con la Puerta del Sol grabada y pintada a mano.',
        'plato,decoracion,tiwanaku'),
    ('ceramica-tiwanaku', 'Macetas',    'Maceta de barro pintada a mano',
        'maceta-barro-pintada',
        'Maceta de barro cocido con motivos geometricos pintados a mano. Con plato base.',
        'maceta,barro,jardin'),
    ('ceramica-tiwanaku', 'Decoracion', 'Florero de ceramica esmaltada',
        'florero-ceramica-esmaltada',
        'Florero de ceramica esmaltada en azul cobalto, altura 25 cm.',
        'florero,ceramica,decoracion')
) AS d(slug, categoria, nombre, pslug, descripcion, etiquetas)
WHERE NOT EXISTS (
    SELECT 1 FROM producto p
    WHERE p.tienda_id = (SELECT id FROM tienda WHERE slug = d.slug)
      AND p.slug = d.pslug
);

-- ----------------------------------------------------------------------------
-- 7. Variantes
--    Incluye casos con precio_oferta, multiples variantes y stock en 0/bajo.
-- ----------------------------------------------------------------------------
INSERT INTO variante
    (nombre, sku, producto_id, precio, precio_oferta, stock, stock_minimo,
     atributos, activa)
SELECT
    d.vnombre, d.sku,
    (SELECT p.id FROM producto p
       WHERE p.tienda_id = (SELECT id FROM tienda WHERE slug = d.slug)
         AND p.slug = d.pslug
       LIMIT 1),
    d.precio::numeric, d.precio_oferta::numeric, d.stock, d.stock_minimo,
    d.atributos::jsonb, true
FROM (VALUES
    -- Textiles Los Andes
    ('textiles-los-andes', 'aguayo-tradicional-paceno', 'Unica', 'AGU-TRAD-U', 180.00, NULL,   15, 5, '{}'),
    ('textiles-los-andes', 'aguayo-grande-multicolor',  'Unica', 'AGU-GRD-U',  240.00, NULL,    2, 3, '{}'),
    ('textiles-los-andes', 'poncho-alpaca-cafe', 'Talla M', 'PON-ALP-M', 320.00, 289.90, 5, 2, '{"talla": "M"}'),
    ('textiles-los-andes', 'poncho-alpaca-cafe', 'Talla L', 'PON-ALP-L', 340.00, NULL,   3, 2, '{"talla": "L"}'),
    ('textiles-los-andes', 'chalina-de-alpaca',  'Gris',  'CHAL-ALP-GRIS',  95.00, NULL, 20, 5, '{"color": "Gris"}'),
    ('textiles-los-andes', 'chalina-de-alpaca',  'Beige', 'CHAL-ALP-BEIGE', 95.00, NULL,  0, 5, '{"color": "Beige"}'),
    -- Sabores de Bolivia
    ('sabores-de-bolivia', 'cafe-altura-yungas-250g', 'Molido', 'CAF-YUN-MOL', 55.00, NULL, 40, 10, '{"presentacion": "Molido"}'),
    ('sabores-de-bolivia', 'cafe-altura-yungas-250g', 'Grano',  'CAF-YUN-GRA', 55.00, NULL, 35, 10, '{"presentacion": "Grano"}'),
    ('sabores-de-bolivia', 'cafe-organico-caranavi-500g', 'Grano', 'CAF-CAR-GRA', 110.00, 99.00, 18, 5, '{"presentacion": "Grano"}'),
    ('sabores-de-bolivia', 'chocolate-70-cacao-boliviano', 'Barra 100g', 'CHO-70-100', 28.00, NULL, 60, 15, '{}'),
    ('sabores-de-bolivia', 'quinua-pop-con-miel', 'Bolsa 80g', 'QUI-POP-80', 15.00, NULL, 50, 10, '{}'),
    -- Tecno Oriente
    ('tecno-oriente', 'funda-silicona-celular', 'Negro',        'FUN-SIL-NEG', 45.00, NULL,  30, 8, '{"color": "Negro"}'),
    ('tecno-oriente', 'funda-silicona-celular', 'Azul',         'FUN-SIL-AZU', 45.00, NULL,  25, 8, '{"color": "Azul"}'),
    ('tecno-oriente', 'funda-silicona-celular', 'Transparente', 'FUN-SIL-TRA', 45.00, 35.00, 18, 8, '{"color": "Transparente"}'),
    ('tecno-oriente', 'audifonos-inalambricos-tws', 'Unica', 'AUD-TWS-U', 220.00, 189.00, 12, 4, '{}'),
    ('tecno-oriente', 'parlante-bluetooth-portatil', 'Unica', 'PAR-BT-U',  180.00, NULL,    0, 3, '{}'),
    ('tecno-oriente', 'cargador-rapido-usbc-20w', 'Unica', 'CAR-USBC-20',  60.00, NULL,   40, 10, '{}'),
    -- Ceramica Tiwanaku
    ('ceramica-tiwanaku', 'juego-tazas-andinas-x4', 'Unica', 'TAZ-AND-X4', 140.00, NULL, 10, 3, '{}'),
    ('ceramica-tiwanaku', 'plato-decorativo-tiwanaku', 'Mediano', 'PLA-TIW-MED', 85.00,  NULL,   14, 4, '{"tamano": "Mediano"}'),
    ('ceramica-tiwanaku', 'plato-decorativo-tiwanaku', 'Grande',  'PLA-TIW-GRA', 130.00, 115.00,  6, 3, '{"tamano": "Grande"}'),
    ('ceramica-tiwanaku', 'maceta-barro-pintada', 'Chica',  'MAC-BAR-CHI', 35.00, NULL, 25, 6, '{"tamano": "Chica"}'),
    ('ceramica-tiwanaku', 'maceta-barro-pintada', 'Grande', 'MAC-BAR-GRA', 70.00, NULL, 12, 4, '{"tamano": "Grande"}'),
    ('ceramica-tiwanaku', 'florero-ceramica-esmaltada', 'Unica', 'FLO-CER-U', 95.00, NULL, 8, 3, '{}')
) AS d(slug, pslug, vnombre, sku, precio, precio_oferta, stock, stock_minimo, atributos)
WHERE NOT EXISTS (
    SELECT 1 FROM variante v
    WHERE v.producto_id = (
              SELECT p.id FROM producto p
              WHERE p.tienda_id = (SELECT id FROM tienda WHERE slug = d.slug)
                AND p.slug = d.pslug
              LIMIT 1)
      AND v.sku = d.sku
);

-- ----------------------------------------------------------------------------
-- 8. Resumen
-- ----------------------------------------------------------------------------
SELECT
    (SELECT count(*) FROM usuario  WHERE email IN
        ('empresa1@kantu.bo','empresa2@kantu.bo','empresa3@kantu.bo','empresa4@kantu.bo')) AS empresas,
    (SELECT count(*) FROM tienda   WHERE slug IN ('textiles-los-andes','sabores-de-bolivia','tecno-oriente','ceramica-tiwanaku')) AS tiendas,
    (SELECT count(*) FROM categoria c JOIN tienda t ON t.id = c.tienda_id
        WHERE t.slug IN ('textiles-los-andes','sabores-de-bolivia','tecno-oriente','ceramica-tiwanaku')) AS categorias,
    (SELECT count(*) FROM producto p JOIN tienda t ON t.id = p.tienda_id
        WHERE t.slug IN ('textiles-los-andes','sabores-de-bolivia','tecno-oriente','ceramica-tiwanaku')) AS productos,
    (SELECT count(*) FROM variante v
        JOIN producto p ON p.id = v.producto_id
        JOIN tienda t ON t.id = p.tienda_id
        WHERE t.slug IN ('textiles-los-andes','sabores-de-bolivia','tecno-oriente','ceramica-tiwanaku')) AS variantes;

COMMIT;
