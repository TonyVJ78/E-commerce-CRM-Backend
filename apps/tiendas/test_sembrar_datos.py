"""Pruebas del comando `sembrar_datos_sinteticos`.

Requieren PostgreSQL: el stock, el total del pedido y el historial de estados
viven en triggers que el comando debe dejar correr.
"""

import os
import tempfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Count, F, Sum
from django.test import TestCase
from django.utils import timezone

from apps.catalogo.models import Producto, Variante, VarianteStockMovimiento
from apps.crm.models import SegmentoCliente
from apps.finanzas.models import GastoOperativo
from apps.ia.models import EventoUsuario
from apps.marketing.models import CuponUso
from apps.pedidos.models import (
    Carrito, HistorialEstadoPedido, ItemPedido, MetodoPago, Pago, Pedido, Resena,
)
from apps.tiendas.management.sintetico import datos
from apps.tiendas.models import Tienda
from apps.usuarios.models import Rol, Usuario

HASTA = date(2026, 11, 19)
PARAMETROS = {'meses': 2, 'clientes': 8, 'pedidos': 30, 'semilla': 7, 'hasta': HASTA}
INICIO = date(2026, 9, 1)


def sembrar(empresa, **extra):
    salida = StringIO()
    call_command('sembrar_datos_sinteticos', empresa=empresa.email, stdout=salida, **{**PARAMETROS, **extra})
    return salida.getvalue()


def revertir(empresa):
    salida = StringIO()
    call_command('sembrar_datos_sinteticos', empresa=empresa.email, revertir=True, stdout=salida)
    return salida.getvalue()


def huella(tienda):
    """Contenido de los pedidos sin ids ni claves, para comparar dos siembras."""
    return list(
        Pedido.objects.filter(tienda=tienda).order_by('fecha', 'cliente__email', 'id')
        .values_list('cliente__email', 'fecha', 'total', 'estado_actual')
    ) + list(
        ItemPedido.objects.filter(tienda=tienda).order_by('pedido__fecha', 'pedido__cliente__email', 'pedido_id', 'variante__sku')
        .values_list('variante__sku', 'cantidad', 'precio_unitario', 'costo_unitario')
    )


class SembrarDatosSinteticosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Usuario.objects.create_user(
            'empresa.siembra@test.bo', 'Password123!', rol=Rol.objects.get(nombre='empresa'))

    def tienda(self):
        return Tienda.objects.get(propietario=self.empresa, nombre=datos.NOMBRE_TIENDA)

    def test_crea_los_conteos_pedidos(self):
        sembrar(self.empresa)
        tienda = self.tienda()
        clientes = Usuario.objects.filter(email__endswith=f'@{datos.DOMINIO_CLIENTES}')
        self.assertEqual(clientes.count(), PARAMETROS['clientes'])
        self.assertTrue(all(c.rol.nombre == 'cliente' for c in clientes))
        self.assertEqual(Pedido.objects.filter(tienda=tienda).count(), PARAMETROS['pedidos'])
        self.assertEqual(Pago.objects.filter(tienda=tienda).count(), PARAMETROS['pedidos'])
        self.assertGreaterEqual(Producto.objects.filter(tienda=tienda).count(), 25)
        self.assertGreater(ItemPedido.objects.filter(tienda=tienda).count(), PARAMETROS['pedidos'])
        self.assertGreater(Resena.objects.filter(tienda=tienda).count(), 0)
        self.assertGreater(GastoOperativo.objects.filter(tienda=tienda).count(), 0)
        self.assertGreater(SegmentoCliente.objects.filter(tienda=tienda).count(), 0)
        eventos = {e['tipo_evento']: e['n'] for e in EventoUsuario.objects.filter(tienda=tienda)
                   .values('tipo_evento').annotate(n=Count('id'))}
        self.assertGreater(eventos['VIEW'], eventos['CART'])
        self.assertGreater(eventos['CART'], PARAMETROS['pedidos'])
        self.assertTrue(Carrito.objects.filter(tienda=tienda).exists())

    def test_totales_de_pedido_cuadran_con_sus_items(self):
        sembrar(self.empresa)
        tienda = self.tienda()
        con_cupon = set(CuponUso.objects.filter(tienda=tienda).values_list('pedido_id', flat=True))
        for pedido in Pedido.objects.filter(tienda=tienda):
            suma = pedido.items.aggregate(s=Sum(F('cantidad') * F('precio_unitario')))['s']
            self.assertEqual(pedido.subtotal, suma, pedido.id)
            if pedido.id in con_cupon:
                self.assertLess(pedido.total, pedido.subtotal)
            else:
                self.assertEqual(pedido.total, pedido.subtotal)
            pago = pedido.pagos.get()
            self.assertEqual(pago.monto, pedido.total)

    def test_costo_se_copia_de_la_variante_y_el_stock_cuadra(self):
        sembrar(self.empresa)
        tienda = self.tienda()
        for item in ItemPedido.objects.filter(tienda=tienda).select_related('variante'):
            self.assertIsNotNone(item.costo_unitario)
            self.assertEqual(item.costo_unitario, item.variante.costo_unitario)
            self.assertLess(item.costo_unitario, item.precio_unitario)
        for variante in Variante.objects.filter(producto__tienda=tienda):
            vendidas = variante.items_pedido.aggregate(s=Sum('cantidad'))['s'] or 0
            carga = VarianteStockMovimiento.objects.filter(variante=variante).first()
            inicial = carga.delta if carga else 0
            self.assertEqual(variante.stock + vendidas, inicial, variante.sku)
            self.assertGreaterEqual(variante.stock, 0)

    def test_fechas_dentro_del_rango_e_historial_coherente(self):
        sembrar(self.empresa)
        tienda = self.tienda()
        fin = timezone.make_aware(datetime(2026, 11, 19, 23, 59, 59))
        inicio = timezone.make_aware(datetime(2026, 9, 1))
        for pedido in Pedido.objects.filter(tienda=tienda).prefetch_related('historial_estados', 'envios'):
            self.assertTrue(inicio <= pedido.fecha <= fin, pedido.fecha)
            historial = sorted(pedido.historial_estados.all(), key=lambda h: (h.fecha, h.id))
            self.assertEqual(historial[0].estado, 'pendiente')
            self.assertEqual(historial[-1].estado, pedido.estado_actual)
            self.assertEqual(historial[0].fecha, pedido.fecha)
            self.assertTrue(all(h.fecha <= fin for h in historial))
            if pedido.estado_actual == 'entregado':
                self.assertEqual([h.estado for h in historial], ['pendiente', 'procesado', 'enviado', 'entregado'])
                dias = (historial[-1].fecha - pedido.fecha) / timedelta(days=1)
                self.assertTrue(1 <= dias <= 7, dias)
                envio = pedido.envios.get()
                self.assertEqual(envio.fecha_entrega, historial[-1].fecha)
        self.assertEqual(HistorialEstadoPedido.objects.filter(tienda=tienda).exclude(fecha__lte=fin).count(), 0)
        for fecha in GastoOperativo.objects.filter(tienda=tienda).values_list('fecha', flat=True):
            self.assertTrue(INICIO <= fecha <= HASTA, fecha)
        for resena in Resena.objects.filter(tienda=tienda):
            self.assertTrue(inicio <= resena.fecha <= fin)
        for evento in EventoUsuario.objects.filter(tienda=tienda):
            self.assertTrue(inicio - timedelta(hours=4) <= evento.fecha <= fin)

    def test_misma_semilla_mismos_datos_y_otra_semilla_distintos(self):
        sembrar(self.empresa)
        primera = huella(self.tienda())
        revertir(self.empresa)
        sembrar(self.empresa)
        self.assertEqual(huella(self.tienda()), primera)
        revertir(self.empresa)
        sembrar(self.empresa, semilla=8)
        self.assertNotEqual(huella(self.tienda()), primera)

    def test_revertir_no_toca_datos_que_no_creo(self):
        otra_empresa = Usuario.objects.create_user(
            'otra.empresa@test.bo', 'Password123!', rol=Rol.objects.get(nombre='empresa'))
        ajena = Tienda.objects.create(propietario=otra_empresa, nombre='Tienda real')
        producto = Producto.objects.create(tienda=ajena, nombre='Producto real')
        variante = Variante.objects.create(producto=producto, sku='REAL-1', precio=Decimal('10.00'), stock=5)
        cliente_real = Usuario.objects.create_user(
            'cliente.real@test.bo', 'Password123!', rol=Rol.objects.get(nombre='cliente'))
        parecido = Usuario.objects.create_user(
            f'e999-x@{datos.DOMINIO_CLIENTES}', 'Password123!', rol=Rol.objects.get(nombre='cliente'))
        pedido = Pedido.objects.create(cliente=cliente_real, tienda=ajena, subtotal=0, total=0)
        ItemPedido.objects.create(tienda=ajena, pedido=pedido, variante=variante, cantidad=2, precio_unitario=10)
        antes = {m: m.objects.count() for m in (Usuario, Tienda, Producto, Variante, Pedido, ItemPedido,
                                                 HistorialEstadoPedido, MetodoPago)}

        sembrar(self.empresa)
        self.assertGreater(Pedido.objects.count(), antes[Pedido])
        resumen = revertir(self.empresa)

        self.assertIn('Datos sintéticos eliminados', resumen)
        self.assertEqual({m: m.objects.count() for m in antes}, antes)
        self.assertFalse(Tienda.objects.filter(nombre=datos.NOMBRE_TIENDA).exists())
        self.assertTrue(Usuario.objects.filter(pk=parecido.pk).exists())
        variante.refresh_from_db()
        self.assertEqual(variante.stock, 3)
        self.assertEqual(revertir(self.empresa).strip(), 'No había datos sintéticos de esa empresa.')

    def test_rechaza_empresa_inexistente_y_doble_siembra(self):
        cliente = Usuario.objects.create_user(
            'solo.cliente@test.bo', 'Password123!', rol=Rol.objects.get(nombre='cliente'))
        with self.assertRaises(CommandError):
            sembrar(cliente)
        sembrar(self.empresa)
        with self.assertRaises(CommandError):
            sembrar(self.empresa)

    def test_reporte_incluye_conteos_y_consultas_sql(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, 'reporte.md')
            sembrar(self.empresa, reporte=ruta)
            with open(ruta, encoding='utf-8') as archivo:
                texto = archivo.read()
        tienda = self.tienda()
        self.assertIn(f'tienda_id = {tienda.id}', texto)
        self.assertIn(f'| pedido | {PARAMETROS["pedidos"]} |', texto)
        self.assertIn(f'SELECT COUNT(*) AS pedido FROM pedido WHERE tienda_id = {tienda.id};', texto)
        self.assertIn('Semilla: `7`', texto)
