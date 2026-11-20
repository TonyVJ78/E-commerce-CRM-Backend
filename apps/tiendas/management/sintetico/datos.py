"""Listas de datos de apoyo para la siembra sintética (nombres, catálogo, comentarios)."""

DOMINIO_CLIENTES = 'sintetico.kantu.bo'
NOMBRE_TIENDA = 'Kantu Demo Analítica'

NOMBRES = [
    'Ana', 'Luis', 'María', 'Carlos', 'Rosa', 'Jorge', 'Lucía', 'Pedro', 'Carmen', 'Juan',
    'Sofía', 'Miguel', 'Elena', 'Fernando', 'Paola', 'Ricardo', 'Daniela', 'Marcelo', 'Valeria',
    'Gustavo', 'Andrea', 'Rodrigo', 'Karen', 'Diego', 'Patricia', 'Álvaro', 'Silvia', 'Mauricio',
    'Gabriela', 'Hugo', 'Natalia', 'Óscar', 'Verónica', 'Sergio', 'Claudia', 'Iván', 'Mónica',
    'Reynaldo', 'Teresa', 'Wilson',
]

APELLIDOS = [
    'Mamani', 'Quispe', 'Flores', 'Choque', 'Condori', 'Gutiérrez', 'Rojas', 'Vargas', 'Fernández',
    'Mendoza', 'Apaza', 'Salazar', 'Cruz', 'Torrez', 'Calle', 'Villca', 'Limachi', 'Rivera',
    'Aguilar', 'Pérez', 'Colque', 'Ramírez', 'Castro', 'Huanca', 'Aliaga', 'Soliz', 'Ortuño',
    'Paz', 'Zeballos', 'Arce', 'Camacho', 'Justiniano', 'Suárez', 'Peñaranda', 'Terrazas',
    'Gonzales', 'Ticona', 'Nina', 'Alanoca', 'Burgoa',
]

# Ciudad -> (peso entre clientes, (mínimo, máximo, más probable) de días de entrega)
CIUDADES = {
    'La Paz': (0.26, (1, 3, 2)),
    'El Alto': (0.14, (1, 3, 2)),
    'Santa Cruz de la Sierra': (0.24, (2, 5, 3)),
    'Cochabamba': (0.17, (2, 5, 3)),
    'Sucre': (0.07, (3, 7, 5)),
    'Oruro': (0.05, (3, 7, 4)),
    'Potosí': (0.03, (4, 7, 6)),
    'Tarija': (0.04, (4, 7, 5)),
}

CALLES = [
    'Av. Camacho', 'Calle Comercio', 'Av. 6 de Agosto', 'Calle Murillo', 'Av. Arce', 'Calle Ayacucho',
    'Av. Busch', 'Calle Sucre', 'Av. América', 'Calle Bolívar', 'Av. Banzer', 'Calle Junín',
]

TRANSPORTISTAS = ['Flota Bolivia', 'Correos de Bolivia', 'Trans Andes Express', 'Envíos Illimani']

BUSQUEDAS = [
    'poncho', 'alpaca', 'zapatillas', 'audífonos', 'café', 'termo', 'chompa', 'regalo', 'miel',
    'smartwatch', 'licuadora', 'sandalias', 'cargador', 'jabón artesanal', 'crema', 'quinua',
    'chocolate', 'ollas', 'bufanda', 'oferta', 'power bank', 'zapatos', 'manta', 'shampoo',
]

CATEGORIAS = [
    'Textiles Andinos',
    'Calzado',
    'Hogar y Cocina',
    'Electrónica',
    'Café y Alimentos',
    'Belleza y Cuidado',
]

# Producto: (nombre, categoría, margen bruto, popularidad, defectos de reseña o None, [(variante, precio Bs)])
# Los márgenes cambian por producto a propósito: electrónica baja, belleza alta y
# la licuadora y el smartwatch casi sin margen.
PRODUCTOS = [
    ('Poncho de alpaca', 'Textiles Andinos', 0.52, 1.0, None,
     [('Azul', '420'), ('Rojo', '420'), ('Natural', '430')]),
    ('Chompa de alpaca trenzada', 'Textiles Andinos', 0.50, 1.3, None,
     [('M', '340'), ('L', '340'), ('XL', '360')]),
    ('Chullo andino tejido', 'Textiles Andinos', 0.58, 2.2, None,
     [('Adulto', '75'), ('Niño', '60')]),
    ('Bufanda de alpaca', 'Textiles Andinos', 0.55, 1.4, None,
     [('Gris', '120'), ('Beige', '120')]),
    ('Guantes de lana', 'Textiles Andinos', 0.56, 1.1, None,
     [('S/M', '60'), ('L/XL', '65')]),
    ('Manta de llama', 'Textiles Andinos', 0.48, 0.6, None,
     [('Individual', '280'), ('Matrimonial', '390')]),
    ('Zapatillas urbanas Kantu', 'Calzado', 0.34, 1.8,
     ['me quedaron chicas aunque pedí mi talla habitual', 'la suela se despegó a las dos semanas',
      'la talla no corresponde, vienen más pequeñas'],
     [('38', '389'), ('40', '389'), ('42', '389'), ('44', '399')]),
    ('Sandalias de cuero', 'Calzado', 0.40, 1.0, None,
     [('37', '160'), ('39', '160'), ('41', '165')]),
    ('Botines de cuero', 'Calzado', 0.30, 0.7, None,
     [('40', '430'), ('42', '430')]),
    ('Zapatos escolares', 'Calzado', 0.36, 1.2, None,
     [('34', '210'), ('36', '210'), ('38', '215'), ('40', '220')]),
    ('Juego de ollas de aluminio 6 piezas', 'Hogar y Cocina', 0.33, 0.8, None,
     [('Único', '520')]),
    ('Termo de acero 1 L', 'Hogar y Cocina', 0.45, 2.0, None,
     [('Negro', '135'), ('Plata', '135'), ('Rojo', '140')]),
    ('Set de tazas de cerámica x6', 'Hogar y Cocina', 0.42, 1.0, None,
     [('Blanco', '95'), ('Artesanal', '120')]),
    ('Licuadora 600 W', 'Hogar y Cocina', 0.12, 1.1, None,
     [('Única', '280')]),
    ('Sartén antiadherente 28 cm', 'Hogar y Cocina', 0.40, 1.3, None,
     [('Única', '110')]),
    ('Audífonos Bluetooth', 'Electrónica', 0.22, 2.0, None,
     [('Negro', '210'), ('Blanco', '210')]),
    ('Cargador rápido USB-C 20 W', 'Electrónica', 0.38, 2.4, None,
     [('Único', '85')]),
    ('Power bank 10000 mAh', 'Electrónica', 0.20, 1.5, None,
     [('Negro', '190'), ('Azul', '190')]),
    ('Parlante portátil', 'Electrónica', 0.16, 1.2, None,
     [('Pequeño', '260'), ('Grande', '390')]),
    ('Smartwatch Fit Pro', 'Electrónica', 0.07, 1.6,
     ['la batería no dura ni un día', 'la pantalla se rayó muy rápido y se desconecta del celular',
      'no mide bien los pasos, muy poco confiable'],
     [('Negro', '480'), ('Rosado', '480')]),
    ('Café de Yungas 500 g', 'Café y Alimentos', 0.32, 2.5, None,
     [('Molido', '78'), ('En grano', '82')]),
    ('Chocolate orgánico 70 %', 'Café y Alimentos', 0.38, 2.0, None,
     [('Barra 100 g', '22'), ('Caja x6', '115')]),
    ('Miel de abeja del Chaco 500 ml', 'Café y Alimentos', 0.30, 1.2, None,
     [('Único', '65')]),
    ('Quinua real 1 kg', 'Café y Alimentos', 0.24, 1.6, None,
     [('Único', '38')]),
    ('Jabón artesanal de quinua', 'Belleza y Cuidado', 0.62, 2.1, None,
     [('Lavanda', '25'), ('Menta', '25')]),
    ('Crema hidratante de aloe', 'Belleza y Cuidado', 0.58, 1.4, None,
     [('100 ml', '55'), ('250 ml', '90')]),
    ('Shampoo de romero 400 ml', 'Belleza y Cuidado', 0.55, 1.3, None,
     [('Único', '48')]),
]

# Multiplicador de demanda por mes (1 = enero) para cada categoría.
ESTACIONALIDAD_CATEGORIA = {
    'Textiles Andinos': {5: 1.2, 6: 1.6, 7: 1.7, 8: 1.5, 9: 1.2, 12: 1.2},
    'Calzado': {1: 1.3, 2: 1.4, 12: 1.2},
    'Hogar y Cocina': {5: 1.2, 12: 1.3},
    'Electrónica': {11: 1.5, 12: 1.7},
    'Café y Alimentos': {7: 1.1, 12: 1.2},
    'Belleza y Cuidado': {5: 1.4, 12: 1.3},
}

COMENTARIOS_POR_NOTA = {
    5: [
        'Excelente producto, llegó antes de lo esperado.',
        'Muy buena calidad, lo recomiendo totalmente.',
        'Superó mis expectativas, volveré a comprar.',
        'Perfecto, tal cual la descripción. Atención de primera.',
        'Me encantó, el empaque muy cuidado y el envío rápido.',
        'Gran relación calidad precio, estoy muy contento.',
        'Todo bien, sin ningún problema. Muy recomendable.',
    ],
    4: [
        'Buen producto, cumple con lo que ofrece.',
        'Muy bueno, solo el envío tardó un poco más de lo previsto.',
        'Me gustó, la calidad es buena por el precio.',
        'Está bien, llegó en buen estado y tal como en las fotos.',
        'Recomendable, aunque el empaque podría ser mejor.',
        'Cumple bien, volvería a comprar en esta tienda.',
    ],
    3: [
        'Regular, esperaba un poco más por el precio.',
        'Cumple pero nada especial, la calidad es normal.',
        'Está aceptable, el envío demoró más de lo indicado.',
        'Producto promedio, tiene detalles pequeños de acabado.',
        'No está mal, pero tampoco me sorprendió.',
    ],
    2: [
        'No es lo que esperaba, la calidad es inferior a las fotos.',
        'Llegó con detalles y tardó mucho en llegar.',
        'Me decepcionó, no lo volvería a comprar.',
        'Mala experiencia con el envío y el producto no era como se mostraba.',
    ],
    1: [
        'Muy mala calidad, no recomiendo esta compra.',
        'Pésima experiencia, el producto llegó dañado.',
        'No funcionó como debía y la atención fue lenta.',
        'Una estafa, nada que ver con la descripción.',
    ],
}

COMENTARIOS_ENVIO_LENTO = [
    'El producto está bien pero el pedido demoró demasiados días en llegar.',
    'La entrega fue muy lenta, casi una semana de espera.',
    'Tardó más de lo prometido, el envío debe mejorar.',
]

COMENTARIOS_TIENDA = {
    5: ['Excelente atención de la tienda, todo llegó perfecto.', 'La mejor tienda para comprar en línea, muy confiable.'],
    4: ['Buena atención y buenos precios, el envío podría ser más rápido.'],
    3: ['La atención es regular, tardaron en responder mis consultas.'],
    2: ['Tardaron mucho en despachar mi pedido y no avisaron.'],
    1: ['Muy mal servicio, nadie respondió mis mensajes.'],
}

OBSERVACIONES_ESTADO = {
    'pendiente': 'Pedido recibido',
    'procesado': 'Pago verificado y pedido en preparación',
    'enviado': 'Pedido despachado con el transportista',
    'entregado': 'Pedido entregado al cliente',
}

MOTIVOS_CANCELACION = [
    'Cancelado por el cliente antes del despacho',
    'No se confirmó el pago del pedido',
    'El cliente solicitó cambiar de producto y canceló',
]


def prefijo_correo(id_empresa):
    return f'e{id_empresa}-'
