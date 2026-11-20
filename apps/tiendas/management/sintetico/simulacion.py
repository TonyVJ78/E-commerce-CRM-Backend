"""Simulación en memoria de 12 meses de una tienda: no toca la base de datos.

Todo sale de un único `random.Random(semilla)`, así que con los mismos
parámetros (y la misma fecha de corte) se obtienen exactamente los mismos datos.
"""

import bisect
import calendar
import itertools
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from apps.pedidos import estados

from . import datos

ZONA = timezone.get_current_timezone()
CENTAVO = Decimal('0.01')

PERFILES = [
    ('curioso', 0.05, (0, 0)),
    ('unico', 0.50, (1, 1)),
    ('ocasional', 0.27, (2, 3)),
    ('frecuente', 0.13, (4, 8)),
    ('fiel', 0.05, (9, 18)),
]
PERFILES_ANTIGUOS = {'frecuente', 'fiel'}

ESTACIONALIDAD_MES = {1: 0.85, 2: 0.80, 3: 0.90, 4: 0.92, 5: 1.0, 6: 0.98,
                      7: 1.0, 8: 0.97, 9: 1.0, 10: 1.08, 11: 1.55, 12: 1.85}
PESO_DIA_SEMANA = [0.90, 0.90, 0.95, 1.0, 1.15, 1.35, 1.20]
PESO_HORA = [1, 1, 1, 1, 1, 2, 3, 5, 7, 9, 10, 11, 12, 11, 9, 8, 8, 9, 11, 13, 14, 12, 7, 3]

PROB_CANCELACION = 0.07
PROB_RESENA = 0.40
PROPORCION_CLIENTES_PREVIOS = 0.60
PROB_RESENA_TIENDA = 0.12
PROB_RECUPERACION = 0.22
RELACION_CARRITOS_ABANDONADOS = 0.28
RELACION_SESIONES_SIN_COMPRA = 2.0
HORAS_INACTIVIDAD_CAMPANA = 2
INICIO_CAMPANA = 0.25

METODOS_PAGO = ['Efectivo', 'QR', 'Tarjeta (Stripe)']
PESOS_METODOS_PAGO = [25, 45, 30]

PESOS_NOTA = [4, 6, 12, 33, 45]
PESOS_NOTA_PRODUCTO_MALO = [21, 25, 22, 20, 12]

# Fracciones de la utilidad bruta mensual promedio (G) que se gastan por concepto.
GASTO_ALQUILER = 0.11
GASTO_SUELDOS = (0.11, 0.08)
GASTO_SERVICIOS = (0.020, 0.010)
GASTO_OTROS = 0.012
TASA_MARKETING = (0.05, 0.08)
TASA_IMPUESTO_TRANSACCIONES = 0.03
COSTO_ENVIO_POR_PEDIDO = Decimal('6.50')

CUPONES_SIEMPRE = [
    ('BIENVENIDO10', 'porcentaje', 10, 0, 0.18, 'primera_compra'),
    ('VUELVE10', 'porcentaje', 10, 0, 0.60, 'recuperado'),
]
# código base, (mes, día) inicio, (mes, día) fin, tipo, valor, monto mínimo, probabilidad de uso
CUPONES_DE_TEMPORADA = [
    ('VERANO', (1, 5), (2, 15), 'monto_fijo', 40, 300, 0.20),
    ('MADRES', (5, 20), (5, 27), 'porcentaje', 12, 100, 0.22),
    ('BLACK', (11, 21), (11, 30), 'porcentaje', 20, 150, 0.30),
    ('NAVIDAD', (12, 10), (12, 25), 'monto_fijo', 30, 200, 0.25),
]


@dataclass(eq=False)
class ProductoSim:
    nombre: str
    categoria: str
    popularidad: float
    defectos: list | None
    variantes: list = field(default_factory=list)
    db: object = None


@dataclass(eq=False)
class VarianteSim:
    producto: ProductoSim
    nombre: str
    sku: str
    precio: Decimal
    costo: Decimal
    unidades_vendidas: int = 0
    stock_final: int = 0
    stock_minimo: int = 5
    db: object = None


@dataclass(eq=False)
class ClienteSim:
    indice: int
    nombre: str
    apellido: str
    email: str
    perfil: str
    registro: datetime
    ciudad: str
    direccion: str
    referencia: str
    db: object = None
    direccion_db: object = None


@dataclass(eq=False)
class CuponSim:
    codigo: str
    tipo: str
    valor: int
    inicio: date
    fin: date
    monto_minimo: int
    probabilidad: float
    condicion: str | None
    usos: int = 0
    db: object = None


@dataclass(eq=False)
class CarritoSim:
    cliente: ClienteSim
    fecha: datetime
    items: list
    notificado: datetime | None = None
    pedido: object = None
    db: object = None


@dataclass(eq=False)
class PedidoSim:
    cliente: ClienteSim
    fecha: datetime
    items: list
    carrito: CarritoSim | None = None
    subtotal: Decimal = Decimal('0.00')
    descuento: Decimal = Decimal('0.00')
    cupon: CuponSim | None = None
    tipo_cambio: Decimal | None = None
    estado: str = estados.PENDIENTE
    historial: list = field(default_factory=list)
    fecha_envio: datetime | None = None
    fecha_entrega: datetime | None = None
    metodo_pago: str = 'Efectivo'
    pago_estado: str = 'pendiente'
    pago_fecha: datetime | None = None
    pago_referencia: str = ''
    db: object = None

    @property
    def total(self):
        return self.subtotal - self.descuento

    @property
    def costo(self):
        return sum((v.costo * cantidad for v, cantidad in self.items), Decimal('0.00'))


@dataclass(eq=False)
class ResenaSim:
    cliente: ClienteSim
    producto: ProductoSim | None
    nota: int
    comentario: str
    fecha: datetime


@dataclass(eq=False)
class EventoSim:
    cliente: ClienteSim | None
    producto: ProductoSim | None
    tipo: str
    fecha: datetime
    termino: str = ''
    canal: str = 'web'


@dataclass(eq=False)
class GastoSim:
    categoria: str
    descripcion: str
    monto: Decimal
    fecha: date


@dataclass(eq=False)
class Simulacion:
    calendario: 'Calendario'
    productos: list
    clientes: list
    cupones: list
    carritos: list
    pedidos: list
    resenas: list
    eventos: list
    gastos: list


def sin_tildes(texto):
    return unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode().lower()


def dinero(valor):
    return Decimal(str(valor)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def restar_meses(dia, meses):
    total = dia.year * 12 + dia.month - 1 - meses
    return date(total // 12, total % 12 + 1, 1)


class Calendario:
    """Días del periodo con su peso de demanda (crecimiento, estacionalidad, fin de semana)."""

    def __init__(self, hasta, meses, ahora):
        self.hasta = hasta
        self.ahora = ahora
        self.inicio = restar_meses(hasta.replace(day=1), meses)
        total_dias = (hasta - self.inicio).days + 1
        self.dias = [self.inicio + timedelta(days=i) for i in range(total_dias)]
        self.acumulado = list(itertools.accumulate(
            self._peso(i, dia, total_dias) for i, dia in enumerate(self.dias)
        ))
        self.meses = sorted({(dia.year, dia.month) for dia in self.dias})

    @staticmethod
    def _peso(i, dia, total_dias):
        crecimiento = 0.80 + 0.45 * i / max(total_dias - 1, 1)
        peso = crecimiento * ESTACIONALIDAD_MES[dia.month] * PESO_DIA_SEMANA[dia.weekday()]
        if dia.month == 12 and 15 <= dia.day <= 24:
            peso *= 1.25
        return peso

    @property
    def ultimo_indice(self):
        return len(self.dias) - 1

    def indice(self, momento):
        """Posición del día del momento en el periodo; negativa si es anterior al inicio."""
        return (momento.astimezone(ZONA).date() - self.inicio).days

    def dia_aleatorio(self, rng, desde=0, hasta=None):
        hasta = self.ultimo_indice if hasta is None else hasta
        base = self.acumulado[desde - 1] if desde else 0.0
        objetivo = base + rng.random() * (self.acumulado[hasta] - base)
        return max(desde, min(bisect.bisect_left(self.acumulado, objetivo), hasta))

    def momento(self, rng, indice_dia):
        dia = self.dias[indice_dia]
        horas = range(24)
        if dia == self.ahora.astimezone(ZONA).date():
            horas = range(self.ahora.astimezone(ZONA).hour + 1)
        hora = rng.choices(horas, weights=[PESO_HORA[h] for h in horas])[0]
        momento = datetime.combine(dia, time(hora, rng.randrange(60), rng.randrange(60)), tzinfo=ZONA)
        if momento > self.ahora:
            inicio_dia = datetime.combine(dia, time.min, tzinfo=ZONA)
            momento = inicio_dia + (self.ahora - inicio_dia) * rng.random()
        return momento

    def momento_aleatorio(self, rng, desde=0):
        return self.momento(rng, self.dia_aleatorio(rng, desde))


def crear_catalogo(rng):
    productos = []
    for numero, (nombre, categoria, margen, popularidad, defectos, variantes) in enumerate(datos.PRODUCTOS, 1):
        producto = ProductoSim(nombre, categoria, popularidad, defectos)
        for orden, (variante, precio) in enumerate(variantes, 1):
            precio = Decimal(precio)
            margen_variante = margen + rng.uniform(-0.02, 0.02)
            producto.variantes.append(VarianteSim(
                producto=producto,
                nombre=variante,
                sku=f'KDA-{numero:02d}-{orden:02d}',
                precio=precio,
                costo=dinero(precio * Decimal(str(1 - margen_variante))),
            ))
        productos.append(producto)
    return productos


def pesos_productos_por_mes(productos):
    return {
        mes: [
            p.popularidad * datos.ESTACIONALIDAD_CATEGORIA.get(p.categoria, {}).get(mes, 1.0)
            for p in productos
        ]
        for mes in range(1, 13)
    }


def registro_previo(rng, calendario):
    dia = calendario.inicio - timedelta(days=rng.randint(1, 400))
    return datetime.combine(dia, time(rng.randrange(24), rng.randrange(60)), tzinfo=ZONA)


def crear_clientes(rng, calendario, cantidad, id_empresa):
    ciudades = list(datos.CIUDADES)
    pesos_ciudades = [datos.CIUDADES[c][0] for c in ciudades]
    clientes = []
    for indice in range(cantidad):
        perfil = rng.choices([p[0] for p in PERFILES], weights=[p[1] for p in PERFILES])[0]
        nombre = rng.choice(datos.NOMBRES)
        apellido = rng.choice(datos.APELLIDOS)
        tope = calendario.ultimo_indice // 2 if perfil in PERFILES_ANTIGUOS else None
        if rng.random() < PROPORCION_CLIENTES_PREVIOS:
            registro = registro_previo(rng, calendario)
        else:
            registro = calendario.momento(rng, calendario.dia_aleatorio(rng, 0, tope))
        clientes.append(ClienteSim(
            indice=indice,
            nombre=nombre,
            apellido=apellido,
            email=(f'{datos.prefijo_correo(id_empresa)}{sin_tildes(nombre)}.{sin_tildes(apellido)}'
                   f'.{indice + 1:04d}@{datos.DOMINIO_CLIENTES}'),
            perfil=perfil,
            registro=registro,
            ciudad=rng.choices(ciudades, weights=pesos_ciudades)[0],
            direccion=f'{rng.choice(datos.CALLES)} #{rng.randint(100, 2999)}',
            referencia=f'Zona {rng.choice(["Centro", "Norte", "Sur", "Este", "Oeste"])}',
        ))
    return clientes


def planificar_conteos(rng, clientes, objetivo):
    rangos = {nombre: rango for nombre, _, rango in PERFILES}
    conteos = [rng.randint(*rangos[c.perfil]) for c in clientes]
    total = sum(conteos)
    indices = range(len(conteos))
    while total < objetivo:
        conteos[rng.choices(indices, weights=[max(c, 1) for c in conteos])[0]] += 1
        total += 1
    while total > objetivo:
        conteos[rng.choices(indices, weights=conteos)[0]] -= 1
        total -= 1
    return conteos


def elegir_items(rng, productos, pesos_mes, mes):
    cantidad_items = rng.choices([1, 2, 3, 4], weights=[55, 30, 12, 3])[0]
    elegidas = []
    while len(elegidas) < cantidad_items:
        producto = rng.choices(productos, weights=pesos_mes[mes])[0]
        variante = rng.choice(producto.variantes)
        if variante in (v for v, _ in elegidas):
            continue
        pesos_cantidad = [55, 30, 15] if variante.precio < 50 else [75, 18, 7]
        elegidas.append((variante, rng.choices([1, 2, 3], weights=pesos_cantidad)[0]))
    return elegidas


def definir_cupones(calendario):
    cupones = [
        CuponSim(codigo, tipo, valor, calendario.inicio, calendario.hasta + timedelta(days=180),
                 minimo, probabilidad, condicion)
        for codigo, tipo, valor, minimo, probabilidad, condicion in CUPONES_SIEMPRE
    ]
    for anio in sorted({dia.year for dia in calendario.dias}):
        for base, (mi, di), (mf, df), tipo, valor, minimo, probabilidad in CUPONES_DE_TEMPORADA:
            inicio, fin = date(anio, mi, di), date(anio, mf, df)
            if fin < calendario.inicio or inicio > calendario.hasta:
                continue
            cupones.append(CuponSim(f'{base}{anio}', tipo, valor, inicio, fin, minimo, probabilidad, None))
    return cupones


def crear_carritos_abandonados(rng, calendario, clientes, productos, pesos_mes, cantidad):
    carritos = []
    inicio_campana = int(calendario.ultimo_indice * INICIO_CAMPANA)
    for _ in range(cantidad):
        cliente = rng.choice(clientes)
        desde = min(max(calendario.indice(cliente.registro), 0), calendario.ultimo_indice)
        fecha = calendario.momento(rng, calendario.dia_aleatorio(rng, desde))
        carrito = CarritoSim(cliente, fecha, elegir_items(rng, productos, pesos_mes, fecha.month))
        if calendario.indice(fecha) >= inicio_campana:
            carrito.notificado = fecha + timedelta(hours=HORAS_INACTIVIDAD_CAMPANA + rng.uniform(0, 4))
            if carrito.notificado > calendario.ahora:
                carrito.notificado = None
        carritos.append(carrito)
    return carritos


def recuperar_carritos(rng, calendario, carritos):
    """Una parte de los carritos notificados termina en compra; devuelve esos pedidos."""
    pedidos = []
    for carrito in carritos:
        if carrito.notificado is None or rng.random() >= PROB_RECUPERACION:
            continue
        fecha = carrito.notificado + timedelta(minutes=rng.uniform(30, 30 * 60))
        if fecha > calendario.ahora:
            continue
        pedido = PedidoSim(carrito.cliente, fecha, carrito.items, carrito=carrito)
        carrito.pedido = pedido
        pedidos.append(pedido)
    return pedidos


def crear_pedidos_regulares(rng, calendario, clientes, conteos, productos, pesos_mes):
    pedidos = []
    ultimo = calendario.ultimo_indice
    for cliente, cantidad in zip(clientes, conteos):
        if cantidad == 0:
            continue
        registro = calendario.indice(cliente.registro)
        if registro < 0:
            fechas = [calendario.momento_aleatorio(rng) for _ in range(cantidad)]
        else:
            primero = min(registro + int(rng.expovariate(1 / 4)), ultimo)
            fechas = [calendario.momento(rng, primero)]
            fechas += [calendario.momento_aleatorio(rng, primero) for _ in range(cantidad - 1)]
            fechas[0] = min(max(fechas[0], cliente.registro + timedelta(minutes=5)), calendario.ahora)
        for fecha in sorted(fechas):
            pedidos.append(PedidoSim(cliente, fecha, elegir_items(rng, productos, pesos_mes, fecha.month)))
    return pedidos


def aplicar_cupon(rng, pedido, cupones, ya_compro, usos_por_cliente):
    dia = pedido.fecha.astimezone(ZONA).date()
    for cupon in cupones:
        if not cupon.inicio <= dia <= cupon.fin or pedido.subtotal < cupon.monto_minimo:
            continue
        if cupon.condicion == 'primera_compra' and pedido.cliente.indice in ya_compro:
            continue
        if cupon.condicion == 'recuperado' and pedido.carrito is None:
            continue
        if usos_por_cliente[(cupon.codigo, pedido.cliente.indice)] or rng.random() >= cupon.probabilidad:
            continue
        descuento = pedido.subtotal * cupon.valor / 100 if cupon.tipo == 'porcentaje' else Decimal(cupon.valor)
        pedido.cupon = cupon
        pedido.descuento = min(pedido.subtotal, dinero(descuento))
        cupon.usos += 1
        usos_por_cliente[(cupon.codigo, pedido.cliente.indice)] += 1
        return


def asignar_ciclo_de_vida(rng, pedido, ahora):
    inicio = pedido.fecha
    historial = [(estados.PENDIENTE, inicio, datos.OBSERVACIONES_ESTADO[estados.PENDIENTE])]
    if ahora - inicio > timedelta(days=1) and rng.random() < PROB_CANCELACION:
        if rng.random() < 0.4:
            procesado = inicio + timedelta(hours=rng.uniform(1, 12))
            historial.append((estados.PROCESADO, procesado, datos.OBSERVACIONES_ESTADO[estados.PROCESADO]))
            cancelado = procesado + timedelta(hours=rng.uniform(1, 30))
        else:
            cancelado = inicio + timedelta(minutes=rng.uniform(10, 1200))
        historial.append((estados.CANCELADO, min(cancelado, ahora), rng.choice(datos.MOTIVOS_CANCELACION)))
    else:
        minimo, maximo, moda = datos.CIUDADES[pedido.cliente.ciudad][1]
        dias = rng.triangular(minimo, maximo, moda)
        procesado = inicio + timedelta(hours=rng.uniform(1, 12))
        enviado = max(inicio + timedelta(days=dias * rng.uniform(0.35, 0.55)), procesado + timedelta(hours=2))
        entregado = max(inicio + timedelta(days=dias), enviado + timedelta(hours=6))
        for estado, momento in zip(estados.FLUJO[1:], (procesado, enviado, entregado)):
            if momento <= ahora:
                historial.append((estado, momento, datos.OBSERVACIONES_ESTADO[estado]))
    pedido.historial = historial
    pedido.estado = historial[-1][0]
    momentos = {estado: momento for estado, momento, _ in historial}
    pedido.fecha_envio = momentos.get(estados.ENVIADO)
    pedido.fecha_entrega = momentos.get(estados.ENTREGADO)


def asignar_pago(rng, pedido):
    metodo = rng.choices(METODOS_PAGO, weights=PESOS_METODOS_PAGO)[0]
    pedido.metodo_pago = metodo
    pedido.pago_fecha = pedido.fecha
    if metodo == 'Tarjeta (Stripe)':
        pedido.pago_fecha += timedelta(minutes=rng.uniform(1, 3))
        pedido.pago_referencia = f'pi_sint_{rng.getrandbits(56):014x}'
    elif metodo == 'QR':
        pedido.pago_fecha += timedelta(minutes=rng.uniform(5, 120))
        pedido.pago_referencia = f'QR-{rng.randrange(10**8):08d}'
    if pedido.estado == estados.CANCELADO:
        pedido.pago_estado = 'cancelado' if metodo == 'Efectivo' else 'reembolsado'
    elif metodo == 'Efectivo':
        pedido.pago_estado = 'pagado' if pedido.estado == estados.ENTREGADO else 'pendiente'
        pedido.pago_fecha = pedido.fecha_entrega or pedido.fecha
    elif metodo == 'QR' and pedido.estado == estados.PENDIENTE:
        pedido.pago_estado = 'pendiente'
    else:
        pedido.pago_estado = 'pagado'


def crear_pedidos(rng, calendario, clientes, productos, pesos_mes, cupones, carritos, tipos_cambio, objetivo):
    recuperados = recuperar_carritos(rng, calendario, carritos)
    conteos = planificar_conteos(rng, clientes, max(objetivo - len(recuperados), 0))
    pedidos = recuperados + crear_pedidos_regulares(rng, calendario, clientes, conteos, productos, pesos_mes)
    pedidos.sort(key=lambda p: p.fecha)

    ya_compro = set()
    usos_por_cliente = defaultdict(int)
    for pedido in pedidos:
        pedido.subtotal = sum((v.precio * cantidad for v, cantidad in pedido.items), Decimal('0.00'))
        aplicar_cupon(rng, pedido, cupones, ya_compro, usos_por_cliente)
        ya_compro.add(pedido.cliente.indice)
        pedido.tipo_cambio = tipos_cambio.get(pedido.fecha.astimezone(ZONA).date())
        asignar_ciclo_de_vida(rng, pedido, calendario.ahora)
        asignar_pago(rng, pedido)
        for variante, cantidad in pedido.items:
            variante.unidades_vendidas += cantidad
    return pedidos


def definir_stock(rng, calendario, productos):
    variantes = [v for p in productos for v in p.variantes]
    meses = len(calendario.dias) / 30.4375
    for variante in variantes:
        por_mes = variante.unidades_vendidas / meses
        variante.stock_final = round(por_mes * rng.uniform(0.5, 2.2))
        variante.stock_minimo = max(5, round(por_mes * 0.5))
    for variante in rng.sample(variantes, max(1, len(variantes) // 8)):
        variante.stock_final = rng.randint(0, variante.stock_minimo - 1)
    for variante in rng.sample(variantes, min(2, len(variantes))):
        variante.stock_final = 0


def calificar(rng, pedido, producto):
    pesos = PESOS_NOTA_PRODUCTO_MALO if producto and producto.defectos else PESOS_NOTA
    nota = rng.choices(range(1, 6), weights=pesos)[0]
    entrega_lenta = (pedido.fecha_entrega - pedido.fecha).days >= 5
    if entrega_lenta and rng.random() < 0.45:
        nota = min(nota, rng.choice([2, 3, 3]))
    if producto is None:
        return nota, rng.choice(datos.COMENTARIOS_TIENDA[nota])
    if entrega_lenta and nota <= 3:
        return nota, rng.choice(datos.COMENTARIOS_ENVIO_LENTO)
    if producto.defectos and nota <= 2:
        defecto = rng.choice(producto.defectos)
        return nota, f'{defecto[0].upper()}{defecto[1:]}.'
    return nota, rng.choice(datos.COMENTARIOS_POR_NOTA[nota])


def crear_resenas(rng, calendario, pedidos):
    resenas = []
    ya_califico = set()
    for pedido in pedidos:
        if pedido.estado != estados.ENTREGADO or rng.random() >= PROB_RESENA:
            continue
        producto = None
        if rng.random() >= PROB_RESENA_TIENDA:
            producto = rng.choice(pedido.items)[0].producto
        if (pedido.cliente.indice, producto and producto.nombre) in ya_califico:
            continue
        fecha = pedido.fecha_entrega + timedelta(days=rng.uniform(0.5, 14))
        if fecha > calendario.ahora:
            continue
        ya_califico.add((pedido.cliente.indice, producto and producto.nombre))
        nota, comentario = calificar(rng, pedido, producto)
        resenas.append(ResenaSim(pedido.cliente, producto, nota, comentario, fecha))
    return resenas


def eventos_de_sesion(rng, calendario, cliente, inicio, fin, vistos, con_carrito=()):
    """Embudo de una visita: búsqueda, vistas y clics de lo visto y, al final, lo agregado al carrito."""
    canal = rng.choices(['web', 'movil'], weights=[65, 35])[0]
    duracion = (fin - inicio).total_seconds()

    def evento(producto, tipo, desde, hasta, termino=''):
        momento = inicio + timedelta(seconds=duracion * rng.uniform(desde, hasta))
        return EventoSim(cliente, producto, tipo, min(momento, calendario.ahora), termino, canal)

    eventos = []
    if rng.random() < 0.4:
        eventos.append(evento(None, 'SEARCH', 0, 0.1, rng.choice(datos.BUSQUEDAS)))
    for producto in vistos:
        eventos += [evento(producto, 'VIEW', 0.05, 0.7) for _ in range(rng.randint(1, 3))]
        if rng.random() < 0.6:
            eventos.append(evento(producto, 'CLICK', 0.1, 0.8))
    eventos += [evento(producto, 'CART', 0.8, 0.95) for producto in con_carrito]
    return eventos


def crear_eventos(rng, calendario, clientes, productos, pesos_mes, pedidos, carritos):
    eventos = []
    for pedido in pedidos:
        comprados = [v.producto for v, _ in pedido.items]
        otros = rng.choices(productos, weights=pesos_mes[pedido.fecha.month], k=rng.randint(1, 3))
        inicio = pedido.fecha - timedelta(hours=rng.uniform(0.3, 3))
        eventos += eventos_de_sesion(rng, calendario, pedido.cliente, inicio, pedido.fecha - timedelta(minutes=1),
                                     comprados + otros, con_carrito=comprados)
    for carrito in carritos:
        guardados = [v.producto for v, _ in carrito.items]
        eventos += eventos_de_sesion(rng, calendario, carrito.cliente, carrito.fecha - timedelta(minutes=45),
                                     carrito.fecha, guardados, con_carrito=guardados)
    for _ in range(round(len(pedidos) * RELACION_SESIONES_SIN_COMPRA)):
        inicio = calendario.momento_aleatorio(rng)
        cliente = rng.choice(clientes)
        if rng.random() >= 0.4 or cliente.registro > inicio:
            cliente = None
        vistos = rng.choices(productos, weights=pesos_mes[inicio.month], k=rng.randint(2, 6))
        eventos += eventos_de_sesion(rng, calendario, cliente, inicio, inicio + timedelta(minutes=30), vistos)
    return eventos


def dia_del_mes(anio, mes, dia):
    return date(anio, mes, min(dia, calendar.monthrange(anio, mes)[1]))


def totales_por_mes(pedidos):
    """Ingresos, costo y pedidos entregados por (año, mes), sin contar los cancelados."""
    ingresos, costos, entregados = defaultdict(Decimal), defaultdict(Decimal), defaultdict(int)
    for pedido in pedidos:
        if pedido.estado == estados.CANCELADO:
            continue
        mes = (pedido.fecha.year, pedido.fecha.month)
        ingresos[mes] += pedido.total
        costos[mes] += pedido.costo
        entregados[mes] += pedido.estado == estados.ENTREGADO
    return ingresos, costos, entregados


def crear_gastos(rng, calendario, pedidos):
    ingresos, costos, entregados = totales_por_mes(pedidos)
    utilidad_bruta = {mes: ingresos[mes] - costos[mes] for mes in calendario.meses}
    promedio = float(sum(utilidad_bruta.values())) / (len(calendario.dias) / 30.4375)
    gastos = []

    def agregar(categoria, descripcion, monto, dia):
        monto = dinero(monto)
        if dia <= calendario.hasta and monto > 0:
            gastos.append(GastoSim(categoria, descripcion, monto, dia))

    def redondeado(valor):
        return Decimal(round(valor / 5) * 5)

    for anio, mes in calendario.meses:
        agregar('alquiler', 'Alquiler del local y depósito',
                redondeado(GASTO_ALQUILER * promedio), dia_del_mes(anio, mes, 1))
        agregar('sueldos', 'Sueldo del encargado de ventas',
                redondeado(GASTO_SUELDOS[0] * promedio), dia_del_mes(anio, mes, 28))
        agregar('sueldos', 'Sueldo del personal de almacén y despacho',
                redondeado(GASTO_SUELDOS[1] * promedio), dia_del_mes(anio, mes, 28))
        agregar('servicios', 'Electricidad y agua',
                GASTO_SERVICIOS[0] * promedio * rng.uniform(0.85, 1.15), dia_del_mes(anio, mes, 12))
        agregar('servicios', 'Internet y telefonía',
                redondeado(GASTO_SERVICIOS[1] * promedio), dia_del_mes(anio, mes, 12))
        agregar('otros', 'Insumos de oficina y mantenimiento',
                GASTO_OTROS * promedio * rng.uniform(0.6, 1.4), dia_del_mes(anio, mes, 20))

        dias_marketing = [d for d in (3, 10, 17, 24) if dia_del_mes(anio, mes, d) <= calendario.hasta]
        if dias_marketing:
            gasto_mes = float(ingresos[(anio, mes)]) * rng.uniform(*TASA_MARKETING)
            for dia in dias_marketing:
                agregar('marketing', 'Publicidad en redes sociales',
                        gasto_mes / len(dias_marketing) * rng.uniform(0.85, 1.15), dia_del_mes(anio, mes, dia))

        ultimo_dia = min(dia_del_mes(anio, mes, 31), calendario.hasta)
        agregar('transporte', 'Costo de despachos y embalaje',
                COSTO_ENVIO_POR_PEDIDO * entregados[(anio, mes)], ultimo_dia)

        mes_anterior = (anio, mes - 1) if mes > 1 else (anio - 1, 12)
        if mes_anterior in ingresos:
            agregar('impuestos', 'Impuesto a las transacciones',
                    float(ingresos[mes_anterior]) * TASA_IMPUESTO_TRANSACCIONES, dia_del_mes(anio, mes, 15))

    agregar_gasto_extraordinario(calendario, gastos, utilidad_bruta, promedio)
    return gastos


def agregar_gasto_extraordinario(calendario, gastos, utilidad_bruta, promedio):
    """Si ningún mes cerrado terminó en pérdida, un imprevisto empuja el más flojo a números rojos."""
    completos = [mes for mes in calendario.meses if dia_del_mes(*mes, 31) <= calendario.hasta]
    gasto_mes = defaultdict(Decimal)
    for gasto in gastos:
        gasto_mes[(gasto.fecha.year, gasto.fecha.month)] += gasto.monto
    neto = {mes: utilidad_bruta[mes] - gasto_mes[mes] for mes in completos}
    if not neto or min(neto.values()) < 0:
        return
    mes = min(neto, key=neto.get)
    monto = dinero(neto[mes] + Decimal(str(promedio * 0.12)))
    gastos.append(GastoSim('otros', 'Reparación del depósito y compra de equipos (gasto extraordinario)',
                           monto, dia_del_mes(*mes, 22)))


def simular(rng, calendario, id_empresa, clientes_total, pedidos_total, tipos_cambio):
    productos = crear_catalogo(rng)
    pesos_mes = pesos_productos_por_mes(productos)
    clientes = crear_clientes(rng, calendario, clientes_total, id_empresa)
    cupones = definir_cupones(calendario)
    carritos = crear_carritos_abandonados(
        rng, calendario, clientes, productos, pesos_mes, round(pedidos_total * RELACION_CARRITOS_ABANDONADOS))
    pedidos = crear_pedidos(rng, calendario, clientes, productos, pesos_mes, cupones, carritos,
                            tipos_cambio, pedidos_total)
    definir_stock(rng, calendario, productos)
    return Simulacion(
        calendario=calendario,
        productos=productos,
        clientes=clientes,
        cupones=cupones,
        carritos=carritos,
        pedidos=pedidos,
        resenas=crear_resenas(rng, calendario, pedidos),
        eventos=crear_eventos(rng, calendario, clientes, productos, pesos_mes, pedidos, carritos),
        gastos=crear_gastos(rng, calendario, pedidos),
    )
