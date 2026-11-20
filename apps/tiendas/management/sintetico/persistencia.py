"""Escritura de una `Simulacion` en la base y reversión de lo escrito.

Todo pasa por el ORM para que los triggers de PostgreSQL (stock, total del
pedido, historial de estados) corran igual que en el checkout real.
"""

from contextlib import contextmanager
from datetime import datetime, time

from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils.text import slugify

from apps.catalogo.models import Categoria, Producto, Variante, VarianteStockMovimiento
from apps.crm.models import CampanaCarrito, FichaCliente, RegistroRecuperacionCarrito
from apps.finanzas.models import GastoOperativo
from apps.ia.models import EventoUsuario
from apps.marketing.models import Campana, Cupon, CuponUso
from apps.pedidos.models import (
    Carrito, DireccionEnvio, Envio, HistorialEstadoPedido, ItemCarrito, ItemPedido, MetodoPago, Pago, Pedido, Resena,
)
from apps.tiendas.models import DireccionTienda, Tienda
from apps.usuarios.models import Rol, Usuario

from . import datos
from .simulacion import HORAS_INACTIVIDAD_CAMPANA, ZONA

LOTE = 2000


@contextmanager
def fechas_explicitas(*modelos):
    """Deja que `auto_now_add` respete la fecha que se le da, para escribir historia en el pasado."""
    campos = [f for modelo in modelos for f in modelo._meta.concrete_fields if getattr(f, 'auto_now_add', False)]
    for campo in campos:
        campo.auto_now_add = False
    try:
        yield
    finally:
        for campo in campos:
            campo.auto_now_add = True


MODELOS_CON_FECHA = (
    Tienda, Usuario, Producto, VarianteStockMovimiento, Carrito, RegistroRecuperacionCarrito, CuponUso,
    Pedido, HistorialEstadoPedido, Pago, Resena, EventoUsuario, GastoOperativo,
)


def inicio_del_dia(dia):
    return datetime.combine(dia, time.min, tzinfo=ZONA)


def crear_tienda(empresa, calendario):
    tienda = Tienda.objects.create(
        propietario=empresa,
        nombre=datos.NOMBRE_TIENDA,
        descripcion='Tienda con datos sintéticos de 12 meses para analítica, KPIs y modelos de recomendación.',
        fecha_creacion=inicio_del_dia(calendario.inicio),
    )
    DireccionTienda.objects.create(tienda=tienda, direccion='Av. Montes #845', ciudad='La Paz', telefono='2-2401234')
    return tienda


def crear_clientes(simulacion, tienda):
    rol_cliente = Rol.objects.get(nombre='cliente')
    clave_inutilizable = make_password(None)
    usuarios = Usuario.objects.bulk_create([
        Usuario(email=c.email, first_name=c.nombre, last_name=c.apellido, rol=rol_cliente,
                password=clave_inutilizable, fecha_registro=c.registro, date_joined=c.registro)
        for c in simulacion.clientes
    ], batch_size=LOTE)
    for cliente, usuario in zip(simulacion.clientes, usuarios):
        cliente.db = usuario
    FichaCliente.objects.bulk_create(
        [FichaCliente(cliente=c.db, tienda=tienda) for c in simulacion.clientes], batch_size=LOTE)
    direcciones = DireccionEnvio.objects.bulk_create([
        DireccionEnvio(tienda=tienda, cliente=c.db, direccion=c.direccion, ciudad=c.ciudad,
                       referencia=c.referencia, es_predeterminada=True)
        for c in simulacion.clientes
    ], batch_size=LOTE)
    for cliente, direccion in zip(simulacion.clientes, direcciones):
        cliente.direccion_db = direccion


def crear_catalogo(simulacion, tienda, empresa):
    categorias = {nombre: Categoria.objects.create(tienda=tienda, nombre=nombre) for nombre in datos.CATEGORIAS}
    inicio = inicio_del_dia(simulacion.calendario.inicio)
    for producto in simulacion.productos:
        producto.db = Producto.objects.create(
            tienda=tienda,
            categoria=categorias[producto.categoria],
            nombre=producto.nombre,
            slug=slugify(producto.nombre),
            descripcion=f'{producto.nombre}: producto de la categoría {producto.categoria}.',
            etiquetas=[slugify(producto.categoria)],
            creado=inicio,
        )
    variantes = [v for p in simulacion.productos for v in p.variantes]
    creadas = Variante.objects.bulk_create([
        Variante(producto=v.producto.db, nombre=v.nombre, sku=v.sku, precio=v.precio, costo_unitario=v.costo,
                 stock=v.unidades_vendidas + v.stock_final, stock_minimo=v.stock_minimo,
                 atributos={'variante': v.nombre})
        for v in variantes
    ])
    for variante, fila in zip(variantes, creadas):
        variante.db = fila
    VarianteStockMovimiento.objects.bulk_create([
        VarianteStockMovimiento(
            variante=v.db, previous_stock=0, delta=v.db.stock, resulting_stock=v.db.stock, actor=empresa,
            reason='Carga inicial de inventario (siembra sintética)', created_at=inicio,
        )
        for v in variantes if v.db.stock > 0
    ])


def crear_cupones(simulacion, tienda):
    hasta = simulacion.calendario.hasta
    for cupon in simulacion.cupones:
        campana = Campana.objects.create(
            tienda=tienda, tipo='descuento', nombre=f'Cupón {cupon.codigo}',
            mensaje=f'Descuento con el código {cupon.codigo}.', fecha_inicio=cupon.inicio, fecha_fin=cupon.fin,
        )
        cupon.db = Cupon.objects.create(
            tienda=tienda, campana=campana, codigo=cupon.codigo, tipo_descuento=cupon.tipo, valor_descuento=cupon.valor,
            fecha_inicio=cupon.inicio, fecha_expiracion=cupon.fin, monto_minimo=cupon.monto_minimo,
            usos_maximos=max(cupon.usos * 2, 50), limite_por_cliente=1, activo=cupon.fin >= hasta,
        )


def crear_carritos(simulacion, tienda):
    # activo=False: ninguna tarea programada debe mandar correos a cuentas sintéticas.
    campana = CampanaCarrito.objects.create(
        tienda=tienda, activo=False, horas_inactividad=HORAS_INACTIVIDAD_CAMPANA,
        descuento_porcentaje=10, codigo_cupon='VUELVE10',
    )
    filas = Carrito.objects.bulk_create([
        Carrito(cliente=c.cliente.db, tienda=tienda, fecha_creacion=c.fecha,
                ultima_actividad=c.pedido.fecha if c.pedido else c.fecha)
        for c in simulacion.carritos
    ], batch_size=LOTE)
    for carrito, fila in zip(simulacion.carritos, filas):
        carrito.db = fila
    ItemCarrito.objects.bulk_create([
        ItemCarrito(tienda=tienda, carrito=c.db, variante=variante.db, cantidad=cantidad)
        for c in simulacion.carritos if c.pedido is None
        for variante, cantidad in c.items
    ], batch_size=LOTE)
    return campana


def crear_pedidos(simulacion, tienda):
    pedidos = simulacion.pedidos
    filas = Pedido.objects.bulk_create([
        Pedido(cliente=p.cliente.db, tienda=tienda, estado_actual=p.estado, fecha=p.fecha,
               subtotal=0, total=0, tipo_cambio_usd=p.tipo_cambio)
        for p in pedidos
    ], batch_size=LOTE)
    for pedido, fila in zip(pedidos, filas):
        pedido.db = fila
    # El trigger de estado deja una fila con la hora actual: se reemplaza por la historia simulada.
    HistorialEstadoPedido.objects.filter(tienda=tienda).delete()
    HistorialEstadoPedido.objects.bulk_create([
        HistorialEstadoPedido(tienda=tienda, pedido=p.db, estado=estado, observacion=observacion, fecha=momento)
        for p in pedidos for estado, momento, observacion in p.historial
    ], batch_size=LOTE)
    ItemPedido.objects.bulk_create([
        ItemPedido(tienda=tienda, pedido=p.db, variante=v.db, cantidad=cantidad,
                   precio_unitario=v.precio, costo_unitario=v.costo)
        for p in pedidos for v, cantidad in p.items
    ], batch_size=LOTE)
    con_descuento = [p for p in pedidos if p.cupon]
    for pedido in con_descuento:
        pedido.db.total = pedido.total
    Pedido.objects.bulk_update([p.db for p in con_descuento], ['total'], batch_size=LOTE)
    CuponUso.objects.bulk_create([
        CuponUso(tienda=tienda, cupon=p.cupon.db, pedido=p.db, fecha_uso=p.fecha) for p in con_descuento
    ], batch_size=LOTE)


def crear_pagos_y_envios(simulacion, tienda):
    metodos = {nombre: MetodoPago.objects.get_or_create(nombre=nombre)[0] for nombre in
               {p.metodo_pago for p in simulacion.pedidos}}
    Pago.objects.bulk_create([
        Pago(tienda=tienda, pedido=p.db, metodo_pago=metodos[p.metodo_pago], monto=p.total,
             estado=p.pago_estado, fecha=p.pago_fecha, referencia_transaccion=p.pago_referencia)
        for p in simulacion.pedidos
    ], batch_size=LOTE)
    Envio.objects.bulk_create([
        Envio(tienda=tienda, pedido=p.db, direccion_envio=p.cliente.direccion_db,
              transportista=datos.TRANSPORTISTAS[orden % len(datos.TRANSPORTISTAS)],
              numero_seguimiento=f'KDA-{orden:06d}',
              fecha_envio=p.fecha_envio, fecha_entrega=p.fecha_entrega)
        for orden, p in enumerate(simulacion.pedidos, 1) if p.fecha_envio
    ], batch_size=LOTE)


def crear_recuperaciones(simulacion, campana):
    RegistroRecuperacionCarrito.objects.bulk_create([
        RegistroRecuperacionCarrito(
            campana=campana, carrito=c.db, cliente=c.cliente.db, fecha_envio=c.notificado,
            recuperado=c.pedido is not None, pedido_resultante=c.pedido.db if c.pedido else None,
        )
        for c in simulacion.carritos if c.notificado
    ], batch_size=LOTE)


def crear_resenas(simulacion, tienda):
    Resena.objects.bulk_create([
        Resena(tienda=tienda, cliente=r.cliente.db, producto=r.producto.db if r.producto else None,
               calificacion=r.nota, comentario=r.comentario, fecha=r.fecha)
        for r in simulacion.resenas
    ], batch_size=LOTE)


def crear_eventos(simulacion, tienda):
    EventoUsuario.objects.bulk_create([
        EventoUsuario(cliente=e.cliente.db if e.cliente else None, tienda=tienda,
                      producto=e.producto.db if e.producto else None, tipo_evento=e.tipo,
                      termino_busqueda=e.termino, fecha=e.fecha, metadata={'sintetico': True, 'canal': e.canal})
        for e in simulacion.eventos
    ], batch_size=5000)


def crear_gastos(simulacion, tienda, empresa):
    GastoOperativo.objects.bulk_create([
        GastoOperativo(tienda=tienda, categoria=g.categoria, descripcion=g.descripcion, monto=g.monto,
                       fecha=g.fecha, registrado_por=empresa, creado=inicio_del_dia(g.fecha))
        for g in simulacion.gastos
    ], batch_size=LOTE)


def prefijo_y_dominio(empresa):
    return datos.prefijo_correo(empresa.id), f'@{datos.DOMINIO_CLIENTES}'


def clientes_sinteticos(empresa):
    prefijo, dominio = prefijo_y_dominio(empresa)
    return Usuario.objects.filter(email__startswith=prefijo, email__endswith=dominio)


def tienda_sintetica(empresa):
    return Tienda.objects.filter(propietario=empresa, nombre=datos.NOMBRE_TIENDA).first()


@transaction.atomic
def revertir(empresa):
    """Borra la tienda dedicada (y todo lo que cuelga de ella) y los clientes sintéticos de esa empresa."""
    borrados = {}
    tienda = tienda_sintetica(empresa)
    if tienda:
        # El inventario inicial protege a la variante (PROTECT): hay que quitarlo antes de borrar el catálogo.
        VarianteStockMovimiento.objects.filter(variante__producto__tienda=tienda).delete()
        borrados.update(tienda.delete()[1])
    for modelo, cantidad in clientes_sinteticos(empresa).delete()[1].items():
        borrados[modelo] = borrados.get(modelo, 0) + cantidad
    return borrados
