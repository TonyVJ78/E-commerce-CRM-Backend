"""
Script para poblar Métodos de Pago, Carritos, Pedidos, Pagos,
Bitácora de Accesos y Logs de Auditoría en Kantu Market (Neon Tech).
Permite probar los casos de uso:
- CU02: Login / Bitácora
- CU06: Tiendas y Dashboard Empresa
- CU07: Auditoría y Bitácora (admin)
- CU08/CU09: Catálogo y Productos
- CU11: Carrito de Compras
- Pedidos / Checkout / Historial de Ventas
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import django
from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()


from django.db import transaction
from apps.usuarios.models import Usuario, BitacoraAcceso, LogAuditoria
from apps.tiendas.models import Tienda
from apps.catalogo.models import Producto, Variante
from apps.pedidos.models import (
    MetodoPago, Carrito, ItemCarrito, Pedido, ItemPedido,
    HistorialEstadoPedido, Pago, DireccionEnvio
)


@transaction.atomic
def seed_all():
    print("Iniciando población de Métodos de Pago, Carritos, Pedidos y Auditoría...")

    # 1. Métodos de Pago
    metodos = [
        'QR Simple (BCP / BNB / Mercantil)',
        'Tarjeta de Débito / Crédito',
        'Transferencia Bancaria',
        'Pago Contra Entrega'
    ]
    metodo_objs = {}
    for nombre in metodos:
        m, created = MetodoPago.objects.get_or_create(nombre=nombre)
        metodo_objs[nombre] = m
    print(f"✓ Métodos de pago registrados: {len(metodo_objs)}")

    # Obtener usuarios y tiendas
    admin = Usuario.objects.filter(email='admin@kantu.bo').first()
    clientes = list(Usuario.objects.filter(rol__nombre='cliente'))
    tiendas = list(Tienda.objects.all())

    if not clientes or not tiendas:
        print("Error: Se requieren usuarios clientes y tiendas en la base de datos.")
        return

    tienda_textiles = Tienda.objects.filter(slug='textiles-los-andes').first() or tiendas[0]
    tienda_sabores = Tienda.objects.filter(slug='sabores-de-bolivia').first() or (tiendas[1] if len(tiendas) > 1 else tiendas[0])

    # 2. Carritos de Compras (CU11)
    # Limpiar carritos previos
    Carrito.objects.all().delete()

    c1 = clientes[0]  # cliente1@kantu.bo
    c2 = clientes[1] if len(clientes) > 1 else clientes[0]
    c3 = clientes[2] if len(clientes) > 2 else clientes[0]

    # Carrito 1: cliente1 en Textiles Los Andes
    carrito1 = Carrito.objects.create(cliente=c1, tienda=tienda_textiles)
    vars_textiles = list(Variante.objects.filter(producto__tienda=tienda_textiles, stock__gt=5, activa=True)[:3])
    for v in vars_textiles[:2]:
        ItemCarrito.objects.create(tienda=tienda_textiles, carrito=carrito1, variante=v, cantidad=1)

    # Carrito 2: cliente2 en Sabores de Bolivia
    carrito2 = Carrito.objects.create(cliente=c2, tienda=tienda_sabores)
    vars_sabores = list(Variante.objects.filter(producto__tienda=tienda_sabores, stock__gt=5, activa=True)[:3])
    for v in vars_sabores[:2]:
        ItemCarrito.objects.create(tienda=tienda_sabores, carrito=carrito2, variante=v, cantidad=2)

    # Carrito 3: cliente3 en Textiles Los Andes
    if len(vars_textiles) >= 3:
        carrito3 = Carrito.objects.create(cliente=c3, tienda=tienda_textiles)
        ItemCarrito.objects.create(tienda=tienda_textiles, carrito=carrito3, variante=vars_textiles[2], cantidad=1)

    print(f"✓ Carritos activos creados con ítems: {Carrito.objects.count()} carritos, {ItemCarrito.objects.count()} items.")

    # 3. Direcciones de Envío
    dir1, _ = DireccionEnvio.objects.get_or_create(
        cliente=c1, tienda=tienda_textiles,
        defaults={'direccion': 'Av. 6 de Agosto #2450, Edif. Los Pinos Dpto 4B, La Paz'}
    )
    dir2, _ = DireccionEnvio.objects.get_or_create(
        cliente=c2, tienda=tienda_sabores,
        defaults={'direccion': 'Calle Salamanca #450, Cochabamba'}
    )

    # 4. Pedidos reales con Items y Pagos
    # Limpiar pedidos previos para prueba limpia
    Pedido.objects.all().delete()

    # Pedido 1: ENTREGADO (cliente1 en textiles)
    p1 = Pedido.objects.create(
        cliente=c1,
        tienda=tienda_textiles,
        estado_actual='entregado',
        subtotal=Decimal('0.00'),
        total=Decimal('0.00')
    )
    if vars_textiles:
        v = vars_textiles[0]
        ItemPedido.objects.create(
            tienda=tienda_textiles,
            pedido=p1,
            variante=v,
            cantidad=1,
            precio_unitario=v.precio
        )
    # Registrar pago
    Pago.objects.create(
        tienda=tienda_textiles,
        pedido=p1,
        metodo_pago=metodo_objs['QR Simple (BCP / BNB / Mercantil)'],
        monto=p1.total,
        estado='completado',
        referencia_transaccion='BNB-QR-8829104'
    )

    # Pedido 2: ENVIADO (cliente2 en sabores)
    p2 = Pedido.objects.create(
        cliente=c2,
        tienda=tienda_sabores,
        estado_actual='enviado',
        subtotal=Decimal('0.00'),
        total=Decimal('0.00')
    )
    if vars_sabores:
        v = vars_sabores[0]
        ItemPedido.objects.create(
            tienda=tienda_sabores,
            pedido=p2,
            variante=v,
            cantidad=2,
            precio_unitario=v.precio
        )
    Pago.objects.create(
        tienda=tienda_sabores,
        pedido=p2,
        metodo_pago=metodo_objs['Tarjeta de Débito / Crédito'],
        monto=p2.total,
        estado='completado',
        referencia_transaccion='CYBERSOURCE-VISA-4421'
    )

    # Pedido 3: PENDIENTE (cliente3 en textiles)
    p3 = Pedido.objects.create(
        cliente=c3,
        tienda=tienda_textiles,
        estado_actual='pendiente',
        subtotal=Decimal('0.00'),
        total=Decimal('0.00')
    )
    if len(vars_textiles) > 1:
        v = vars_textiles[1]
        ItemPedido.objects.create(
            tienda=tienda_textiles,
            pedido=p3,
            variante=v,
            cantidad=1,
            precio_unitario=v.precio
        )

    # Refrescar totales calculados automáticamente por triggers
    p1.refresh_from_db()
    p2.refresh_from_db()
    p3.refresh_from_db()
    print(f"✓ Pedidos generados: {Pedido.objects.count()} pedidos.")
    print(f"  - Pedido #{p1.id} (Entregado): Bs {p1.total} (calculado por trigger)")
    print(f"  - Pedido #{p2.id} (Enviado): Bs {p2.total} (calculado por trigger)")
    print(f"  - Pedido #{p3.id} (Pendiente): Bs {p3.total} (calculado por trigger)")
    print(f"  - Historial de estados generados por trigger: {HistorialEstadoPedido.objects.count()} registros.")

    # 5. Bitácora de Accesos (CU07)
    BitacoraAcceso.objects.all().delete()
    now = timezone.now()
    logins_data = [
        (admin, 'admin@kantu.bo', True, '', '190.181.45.12', 'Chrome 128 (Windows 11)', now - timedelta(hours=1)),
        (admin, 'admin@kantu.bo', True, '', '190.181.45.12', 'Chrome 128 (Windows 11)', now - timedelta(days=1, hours=3)),
        (None, 'hacker@malicious.com', False, 'Usuario no encontrado', '45.142.120.8', 'Python-requests/2.31', now - timedelta(hours=5)),
        (None, 'admin@kantu.bo', False, 'Contraseña incorrecta', '186.2.144.90', 'Firefox 129 (Linux)', now - timedelta(hours=6)),
        (tienda_textiles.propietario, tienda_textiles.propietario.email, True, '', '200.87.128.5', 'Safari 17.5 (macOS)', now - timedelta(hours=2)),
        (tienda_sabores.propietario, tienda_sabores.propietario.email, True, '', '181.188.160.22', 'Chrome 128 (Android)', now - timedelta(hours=3)),
        (c1, c1.email, True, '', '190.129.78.33', 'Edge 128 (Windows 10)', now - timedelta(minutes=45)),
        (c2, c2.email, True, '', '186.136.21.14', 'Safari 18.0 (iPhone iOS 18)', now - timedelta(minutes=20)),
        (c3, c3.email, True, '', '201.222.89.50', 'Chrome 128 (Windows 11)', now - timedelta(minutes=10)),
    ]

    for user, email, ok, motivo, ip, disp, fecha in logins_data:
        b = BitacoraAcceso(
            usuario=user,
            email_intento=email,
            exitoso=ok,
            motivo=motivo,
            ip=ip,
            dispositivo=disp,
        )
        b.save()
        BitacoraAcceso.objects.filter(pk=b.pk).update(fecha=fecha)

    print(f"✓ Bitácora de accesos poblada: {BitacoraAcceso.objects.count()} registros.")

    # 6. Logs de Auditoría (CU07)
    LogAuditoria.objects.all().delete()
    logs_data = [
        (admin, 'rol_permiso', 1, 'CREAR', None, {'rol': 'empresa', 'permiso': 'tiendas.crear_producto'}, now - timedelta(days=2)),
        (admin, 'rol_permiso', 2, 'CREAR', None, {'rol': 'empresa', 'permiso': 'tiendas.gestionar_stock'}, now - timedelta(days=2)),
        (admin, 'rol_permiso', 3, 'CREAR', None, {'rol': 'cliente', 'permiso': 'catalogo.ver_productos'}, now - timedelta(days=2)),
        (tienda_textiles.propietario, 'tienda', tienda_textiles.id, 'ACTUALIZAR', {'activa': False}, {'activa': True}, now - timedelta(days=1)),
        (tienda_sabores.propietario, 'producto', vars_sabores[0].producto_id, 'CREAR', None, {'nombre': vars_sabores[0].producto.nombre}, now - timedelta(hours=8)),
        (admin, 'sesion', 1, 'CERRAR_SESION', {'usuario': 'admin@kantu.bo'}, None, now - timedelta(hours=4)),
        (c1, 'pedido', p1.id, 'CREAR', None, {'pedido_id': p1.id, 'total': str(p1.total)}, now - timedelta(hours=3)),
    ]

    for user, tabla, reg_id, accion, anterior, nuevo, fecha in logs_data:
        l = LogAuditoria(
            usuario=user,
            tabla_afectada=tabla,
            registro_id=reg_id,
            accion=accion,
            datos_anteriores=anterior,
            datos_nuevos=nuevo,
        )
        l.save()
        LogAuditoria.objects.filter(pk=l.pk).update(fecha=fecha)

    print(f"✓ Logs de auditoría poblados: {LogAuditoria.objects.count()} registros.")
    print("Población completada con éxito en Neon Tech.")


if __name__ == '__main__':
    seed_all()
