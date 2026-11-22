"""Las 22 comprobaciones BRL: PostgreSQL real aislado; proveedores/Stripe simulados."""
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from unittest import mock
from urllib.error import HTTPError, URLError

import stripe
from django.db import connection, transaction, IntegrityError
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.catalogo.models import Producto, Variante, Categoria
from apps.catalogo.serializers import VarianteInputSerializer
from apps.pedidos.models import Carrito, ItemCarrito, Pedido, ItemPedido
from apps.tiendas.models import Tienda
from apps.usuarios.models import LogAuditoria, Usuario
from .models import TipoCambio
from .conversion import convertir_importe
from .brl import actualizar_brl, guardar_observacion_brl, estado_brl, URL_BRL
from .tests import BaseEmpresas


def observacion(rate='2.00000000', fecha=None):
    return {'date': (fecha or timezone.localdate()).isoformat(), 'base': 'BRL', 'quote': 'BOB', 'rate': rate}


@override_settings(CU39_BRL_ENABLED=True, CU39_BRL_DEMO=True, CU39_BRL_PROVIDER_APPROVED=False, CU39_BRL_MAX_AGE_DAYS=1)
class BrlChecks(BaseEmpresas):
    def setUp(self):
        super().setUp()
        self.producto = Producto.objects.create(tienda=self.tienda, nombre='Producto sintético', slug='brl')
        self.uno = Variante.objects.create(producto=self.producto, sku='BRL-BS', precio=64, stock=10)
        self.dos = Variante.objects.create(producto=self.producto, sku='BRL-USD', precio=80, precio_usd=10, precio_oferta=72, stock=10)
        self.cambio = TipoCambio.objects.create(fecha=timezone.localdate(), usd_bob=8, fuente='DEMO USD')
        guardar_observacion_brl(observacion(), sintetica=True)
        self.carrito = Carrito.objects.create(cliente=self.cliente, tienda=self.tienda)
        ItemCarrito.objects.create(carrito=self.carrito, tienda=self.tienda, variante=self.uno, cantidad=2)

    def detalle(self):
        r = self.client.get(f'/api/catalogo/productos/{self.producto.pk}/')
        self.assertEqual(r.status_code, 200, r.data)
        return r.data

    def iniciar(self, **data):
        with mock.patch('stripe.PaymentIntent.create', return_value=SimpleNamespace(id='pi_brl', client_secret='cs_sintetico')) as create:
            r = self.client.post('/api/pedidos/carrito/pago-intento/', data, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        return r, create.call_args.kwargs

    def confirmar(self, kwargs):
        intent = stripe.PaymentIntent.construct_from({'id': 'pi_brl', 'status': 'succeeded',
            'currency': kwargs['currency'], 'amount': kwargs['amount'], 'metadata': kwargs['metadata']}, 'sk_test_fixture')
        with mock.patch('stripe.PaymentIntent.retrieve', return_value=intent):
            return self.client.post('/api/pedidos/carrito/checkout/', {'metodo_pago': 'stripe', 'payment_intent_id': 'pi_brl'}, format='json')

    def test_BRL_01_conversion_backend_y_direccion(self):
        dato = self.detalle()['visualizacion_brl']
        self.assertEqual((dato['precio_efectivo'], dato['tasa_bob_por_brl'], dato['moneda']), ('32.00', '2.00000000', 'BRL'))

    def test_BRL_02_redondeo_decimal_sin_intermedios(self):
        self.assertEqual(convertir_importe('1.01', bob_por_destino='2'), Decimal('0.51'))
        self.assertEqual(convertir_importe('0', bob_por_destino='2'), Decimal('0.00'))
        with self.assertRaises(ValueError):
            convertir_importe('9999999999.99', bob_por_destino='0.01')

    def test_BRL_03_origen_usd_permanece_intacto(self):
        dato = next(v for v in self.detalle()['variantes'] if v['id'] == self.dos.pk)
        self.assertEqual((dato['precio'], dato['precio_usd'], dato['visualizacion_brl']['precio_efectivo']), ('80.00', '10.00', '36.00'))
        self.dos.refresh_from_db()
        self.assertEqual(self.dos.precio_usd, Decimal('10.00'))

    def test_BRL_04_oferta_y_variante_base(self):
        self.uno.precio_oferta = Decimal('60.00'); self.uno.save()
        dato = self.detalle()
        self.assertEqual((dato['precio_base'], dato['visualizacion_brl']['precio_normal'], dato['visualizacion_brl']['precio_efectivo']), ('60.00', '32.00', '30.00'))

    def test_BRL_05_oferta_cero_no_es_ausencia(self):
        self.uno.precio_oferta = Decimal('0.00'); self.uno.save()
        self.assertEqual(self.detalle()['visualizacion_brl']['precio_efectivo'], '0.00')

    def test_BRL_06_rechazo_de_tasas_invalidas_y_constraint(self):
        for tasa in (None, '0', '-1', 'NaN', 'Infinity', '10000000000', '0.000000001', 'texto'):
            with self.subTest(tasa=tasa), self.assertRaises(ValueError):
                guardar_observacion_brl(observacion(tasa), sintetica=True)
        with self.assertRaises(ValueError):
            guardar_observacion_brl(observacion(fecha=timezone.localdate()+timedelta(days=1)), sintetica=True)
        for tasa in (Decimal('NaN'), Decimal('-1'), Decimal('0')):
            with self.subTest(constraint=str(tasa)), self.assertRaises(IntegrityError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('UPDATE tipo_cambio SET brl_bob=%s WHERE id=%s', [tasa, self.cambio.pk])
        self.cambio.refresh_from_db()
        self.assertEqual(self.cambio.brl_bob, Decimal('2'))

    def test_BRL_07_falta_fila_usd_no_inventa_ni_mezcla(self):
        antes = list(TipoCambio.objects.values())
        r = guardar_observacion_brl(observacion(fecha=timezone.localdate()-timedelta(days=1)), sintetica=True)
        self.assertEqual(r['estado'], 'sin_fila_usd')
        self.assertEqual(list(TipoCambio.objects.values()), antes)

    @override_settings(CU39_BRL_DEMO=False, CU39_BRL_PROVIDER_APPROVED=True)
    def test_BRL_08_proveedor_caido_malformado_y_limite(self):
        antes = list(TipoCambio.objects.values())
        for error in (TimeoutError(), URLError('caída'), HTTPError(URL_BRL, 429, 'limitado', {}, None)):
            with self.subTest(error=type(error).__name__), mock.patch('urllib.request.urlopen', side_effect=error):
                self.assertEqual(actualizar_brl()['estado'], 'proveedor_no_disponible')
        for contenido in (b'no json', b'{}', b'x'*16385):
            with mock.patch('urllib.request.urlopen', return_value=BytesIO(contenido)):
                self.assertEqual(actualizar_brl()['estado'], 'proveedor_no_disponible')
        self.assertEqual(list(TipoCambio.objects.values()), antes)
        with mock.patch('urllib.request.urlopen', return_value=BytesIO(b'{"date":"'+timezone.localdate().isoformat().encode()+b'","base":"BRL","quote":"BOB","rate":2.125}')) as fetch:
            self.assertEqual(actualizar_brl()['estado'], 'guardada')
            self.assertEqual(fetch.call_args.args[0].full_url, URL_BRL)
            self.assertEqual(fetch.call_args.kwargs['timeout'], 10)
        self.cambio.refresh_from_db()
        self.assertEqual(self.cambio.brl_bob, Decimal('2.125'))

    def test_BRL_09_vigencia_y_ultima_observacion_fin_de_semana(self):
        TipoCambio.objects.filter(pk=self.cambio.pk).update(fecha=timezone.localdate()-timedelta(days=2))
        self.assertEqual(estado_brl()['estado'], 'vencida')
        self.assertIsNone(self.detalle()['visualizacion_brl'])
        with override_settings(CU39_BRL_MAX_AGE_DAYS=2):
            self.assertTrue(estado_brl()['disponible'])
            self.assertEqual(estado_brl()['fecha'], (timezone.localdate()-timedelta(days=2)).isoformat())

    def test_BRL_10_idempotencia_y_revision_auditada(self):
        cantidad = LogAuditoria.objects.count()
        self.assertEqual(guardar_observacion_brl(observacion(), sintetica=True)['estado'], 'sin_cambios')
        self.assertEqual(LogAuditoria.objects.count(), cantidad)
        guardar_observacion_brl(observacion('2.50000000'), sintetica=True)
        self.assertEqual(LogAuditoria.objects.count(), cantidad+1)

    def test_BRL_11_actualizar_brl_no_recalcula_originales(self):
        precios = list(Variante.objects.values())
        carritos = list(ItemCarrito.objects.values())
        with mock.patch('apps.catalogo.services.recalcular_precios_usd') as recalcular:
            guardar_observacion_brl(observacion('2.5'), sintetica=True)
        recalcular.assert_not_called()
        self.assertEqual(list(Variante.objects.values()), precios)
        self.assertEqual(list(ItemCarrito.objects.values()), carritos)
        self.cambio.refresh_from_db(); self.assertEqual(self.cambio.usd_bob, Decimal('8'))

    @override_settings(STRIPE_SECRET_KEY='sk_test_fixture')
    def test_BRL_12_mismo_payment_intent_usd(self):
        self.client.force_authenticate(self.cliente)
        _, antes = self.iniciar()
        self.client.get(f'/api/catalogo/productos/{self.producto.pk}/?moneda=BRL')
        _, despues = self.iniciar(moneda='BRL')
        self.assertEqual(antes, despues)
        self.assertEqual((despues['currency'], despues['amount']), ('usd', 1600))
        self.assertNotIn('brl', str(despues).lower())

    @override_settings(STRIPE_SECRET_KEY='sk_test_fixture')
    def test_BRL_13_importe_cliente_manipulado_no_autoriza(self):
        self.client.force_authenticate(self.cliente)
        _, datos = self.iniciar(currency='brl', amount=1, precio_brl='0.01')
        self.assertEqual((datos['currency'], datos['amount']), ('usd', 1600))

    def test_BRL_14_multitenant_y_roles(self):
        url = f'/api/tiendas/{self.tienda.pk}/productos/{self.producto.pk}/'
        for usuario in (None, self.cliente, self.otra_empresa):
            self.client.force_authenticate(usuario)
            self.assertIn(self.client.patch(url, {'precio': '1'}, format='json').status_code, (401,403,404))
        self.client.force_authenticate(self.empresa)
        categoria = Categoria.objects.create(tienda=self.tienda_ajena, nombre='Ajena')
        self.assertEqual(self.client.patch(url, {'categoria_id': categoria.pk}, format='json').status_code, 400)
        self.assertEqual(self.uno.precio, Decimal('64'))

    @override_settings(STRIPE_SECRET_KEY='sk_test_fixture')
    def test_BRL_15_historia_conserva_precio_y_tasa(self):
        self.client.force_authenticate(self.cliente)
        _, datos = self.iniciar()
        self.assertEqual(self.confirmar(datos).status_code, 201)
        antes = (list(Pedido.objects.values()), list(ItemPedido.objects.values()))
        guardar_observacion_brl(observacion('3'), sintetica=True)
        self.assertEqual((list(Pedido.objects.values()), list(ItemPedido.objects.values())), antes)
        pedido = Pedido.objects.get()
        self.assertEqual((pedido.total, pedido.tipo_cambio_usd, pedido.items.get().precio_unitario), (Decimal('128'), Decimal('8'), Decimal('64')))

    @override_settings(STRIPE_SECRET_KEY='sk_test_fixture')
    def test_BRL_16_historial_api_no_usa_brl_actual(self):
        self.client.force_authenticate(self.cliente)
        _, datos = self.iniciar(); self.assertEqual(self.confirmar(datos).status_code, 201)
        antes = self.client.get('/api/pedidos/mis-pedidos/').data
        guardar_observacion_brl(observacion('3'), sintetica=True)
        self.assertEqual(self.client.get('/api/pedidos/mis-pedidos/?moneda=BRL').data, antes)

    def test_BRL_17_sin_tasa_sin_politica_y_demo_sin_red(self):
        with override_settings(CU39_BRL_MAX_AGE_DAYS=None):
            self.assertEqual(estado_brl()['estado'], 'politica_pendiente')
        TipoCambio.objects.filter(pk=self.cambio.pk).update(brl_bob=None, brl_fuente=None, brl_obtenido_en=None)
        self.assertIsNone(self.detalle()['visualizacion_brl'])
        self.assertEqual(estado_brl()['estado'], 'sin_cotizacion')
        with mock.patch('urllib.request.urlopen') as fetch:
            self.assertEqual(actualizar_brl()['estado'], 'proveedor_no_autorizado')
        fetch.assert_not_called()

    def test_BRL_18_lista_ficha_y_variante_coherentes(self):
        for url in ('/api/catalogo/productos/', f'/api/catalogo/tiendas/{self.tienda.pk}/productos/'):
            datos = self.client.get(url).data
            self.assertEqual(datos[0]['visualizacion_brl'], self.detalle()['visualizacion_brl'])
        self.client.force_authenticate(self.empresa)
        url = f'/api/tiendas/{self.tienda.pk}/productos/{self.producto.pk}/'
        self.assertEqual(self.client.patch(url, {'variante_id': self.uno.pk, 'precio': '68.00'}, format='json').status_code, 200)
        datos = self.detalle()
        self.assertEqual(datos['visualizacion_brl']['precio_efectivo'], '34.00')
        self.dos.refresh_from_db(); self.assertEqual((self.dos.precio, self.dos.precio_usd), (Decimal('80'), Decimal('10')))

    def test_BRL_19_no_fijacion_brl_en_api(self):
        self.client.force_authenticate(self.empresa)
        url = f'/api/tiendas/{self.tienda.pk}/productos/{self.producto.pk}/'
        self.assertEqual(self.client.patch(url, {'precio_brl': '1'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'moneda_precio': 'BRL', 'precio': '1'}, format='json').status_code, 400)
        s = VarianteInputSerializer(data={'sku':'PRUEBA', 'stock':1, 'stock_minimo':0, 'precio':1, 'precio_brl':2})
        self.assertFalse(s.is_valid())
        self.uno.refresh_from_db(); self.assertEqual(self.uno.precio, Decimal('64'))

    @override_settings(CU39_BRL_ENABLED=False)
    def test_BRL_20_desactivado_compatible_y_sin_red(self):
        with mock.patch('urllib.request.urlopen') as fetch:
            dato = self.detalle()
            r = self.client.get('/api/finanzas/tipo-cambio/')
            self.assertNotIn('brl', r.data)
            self.assertIsNone(dato['visualizacion_brl'])
            self.assertEqual((dato['precio_base'], dato['variantes'][1]['precio_usd']), ('64.00', '10.00'))
        fetch.assert_not_called()

    def test_BRL_21_una_consulta_tasa_por_catalogo_sin_red(self):
        for i in range(15):
            Variante.objects.create(producto=self.producto, sku=f'BULK-{i}', precio=100+i)
        with CaptureQueriesContext(connection) as consultas, mock.patch('urllib.request.urlopen') as fetch:
            dato = self.detalle()
        self.assertEqual(len(dato['variantes']), 17)
        self.assertEqual(sum('FROM "tipo_cambio"' in q['sql'] for q in consultas), 1)
        fetch.assert_not_called()


class BrlMigrationCheck(TransactionTestCase):
    def test_BRL_22_migracion_aditiva_preserva_historia(self):
        executor = MigrationExecutor(connection)
        vieja, nueva = ('finanzas', '0001_initial'), ('finanzas', '0002_brl_catalogo_opcional')
        try:
            executor.migrate([vieja])
            modelo = executor.loader.project_state([vieja]).apps.get_model('finanzas', 'TipoCambio')
            registro = modelo.objects.create(fecha=timezone.localdate(), usd_bob='8.0000', fuente='DEMO HISTÓRICA')
            u = Usuario.objects.create_user(email='migracion@example.test', password=None)
            tienda = Tienda.objects.create(propietario=u, nombre='Sintética', slug='sintetica')
            p = Producto.objects.create(tienda=tienda, nombre='Legado', slug='legado')
            v = Variante.objects.create(producto=p, sku='LEGADO', precio=64, stock=5)
            pedido = Pedido.objects.create(cliente=u, tienda=tienda, subtotal=64, total=64, tipo_cambio_usd=8)
            ItemPedido.objects.create(tienda=tienda, pedido=pedido, variante=v, cantidad=1, precio_unitario=64)
            antes = (list(Variante.objects.values()), list(Pedido.objects.values()), list(ItemPedido.objects.values()))
            executor = MigrationExecutor(connection); executor.migrate([nueva])
            actual = TipoCambio.objects.get(pk=registro.pk)
            self.assertEqual((actual.usd_bob, actual.brl_bob, actual.brl_fuente, actual.brl_obtenido_en), (Decimal('8'), None, None, None))
            self.assertEqual((list(Variante.objects.values()), list(Pedido.objects.values()), list(ItemPedido.objects.values())), antes)
        finally:
            MigrationExecutor(connection).migrate([nueva])
