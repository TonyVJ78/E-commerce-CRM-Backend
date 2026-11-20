"""Pruebas de finanzas: tipo de cambio (HTTP simulado, nunca la API real), cron, gastos y uso en Stripe/catálogo."""

import json
import urllib.error
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import stripe
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.catalogo.models import Producto, Variante
from apps.pedidos.models import Carrito, ItemCarrito, Pedido
from apps.tiendas.models import Tienda
from apps.usuarios.models import Rol, Usuario

from .models import GastoOperativo, TipoCambio
from .tipo_cambio import (
    RespuestaInvalida,
    actualizar_tipo_cambio,
    parsear_historial,
    tipo_cambio_vigente,
)

CONSULTA = 'apps.finanzas.tipo_cambio._consultar_historial'


def item(fecha, usd=11.68, ufv=3.37727, **extra):
    return {
        'fecha': fecha,
        'usd_bob': usd,
        'ufv_bob': ufv,
        'fuente': 'Banco Central de Bolivia',
        'vigencia_usd': 'VIGENCIA: JUEVES 19 DE NOVIEMBRE DE 2026',
        **extra,
    }


def sobre(*items, ok=True):
    return {'ok': ok, 'datos': list(items), 'error': None, 'timestamp': '2026-11-19T10:00:00+00:00'}


def hoy():
    return timezone.localdate()


class ParseoTests(SimpleTestCase):
    def test_parsea_cotizaciones_validas(self):
        [c] = parsear_historial(sobre(item('2026-11-19')))

        self.assertEqual(c['fecha'], date(2026, 11, 19))
        self.assertEqual(c['usd_bob'], Decimal('11.6800'))
        self.assertEqual(c['ufv_bob'], Decimal('3.37727'))
        self.assertEqual(c['fuente'], 'Banco Central de Bolivia')

    def test_ufv_ausente_queda_en_none(self):
        [c] = parsear_historial(sobre(item('2026-11-19', ufv=None)))

        self.assertIsNone(c['ufv_bob'])

    def test_rechaza_ok_distinto_de_true(self):
        with self.assertRaises(RespuestaInvalida):
            parsear_historial(sobre(item('2026-11-19'), ok=False))

    def test_rechaza_datos_que_no_son_lista(self):
        with self.assertRaises(RespuestaInvalida):
            parsear_historial({'ok': True, 'datos': {'usd_bob': 11.68}})

    def test_rechaza_cuando_ninguna_cotizacion_es_valida(self):
        malas = [
            item('2026-11-19', usd=0),
            item('2026-11-19', usd=-3),
            item('2026-11-19', usd='abc'),
            item('2026-11-19', usd=None),
            item('2026-11-19', usd=True),
            item('2026-13-45'),
            item(None),
            'texto',
        ]
        for mala in malas:
            with self.subTest(mala=mala), self.assertRaises(RespuestaInvalida), self.assertLogs(level='WARNING'):
                parsear_historial(sobre(mala))

    def test_descarta_la_cotizacion_mala_y_conserva_las_buenas(self):
        with self.assertLogs(level='WARNING'):
            cotizaciones = parsear_historial(sobre(item('2026-11-19'), item('2026-11-18', usd=0)))

        self.assertEqual([c['fecha'] for c in cotizaciones], [date(2026, 11, 19)])

    def test_rechaza_ufv_no_positiva(self):
        with self.assertLogs(level='WARNING'), self.assertRaises(RespuestaInvalida):
            parsear_historial(sobre(item('2026-11-19', ufv=-1)))


class ActualizarTipoCambioTests(TestCase):
    def test_guarda_las_cotizaciones_por_fecha(self):
        with mock.patch(CONSULTA, return_value=sobre(item('2026-11-19'), item('2026-11-18', usd=11.75))):
            guardadas = actualizar_tipo_cambio(2)

        self.assertEqual(guardadas, 2)
        self.assertEqual(TipoCambio.objects.get(fecha=date(2026, 11, 18)).usd_bob, Decimal('11.7500'))

    def test_es_idempotente_y_actualiza_la_fecha_existente(self):
        with mock.patch(CONSULTA, return_value=sobre(item('2026-11-19'))):
            actualizar_tipo_cambio()
            actualizar_tipo_cambio()
        with mock.patch(CONSULTA, return_value=sobre(item('2026-11-19', usd=11.9))):
            actualizar_tipo_cambio()

        self.assertEqual(TipoCambio.objects.count(), 1)
        self.assertEqual(TipoCambio.objects.get().usd_bob, Decimal('11.9000'))

    def test_pide_el_historial_con_timeout_corto(self):
        respuesta = mock.MagicMock()
        respuesta.__enter__.return_value = respuesta
        respuesta.read.return_value = b'{"ok": true, "datos": [{"fecha": "2026-11-19", "usd_bob": 11.68}]}'
        with mock.patch('urllib.request.urlopen', return_value=respuesta) as urlopen:
            guardadas = actualizar_tipo_cambio(5)

        solicitud = urlopen.call_args.args[0]
        self.assertEqual(solicitud.full_url, 'https://api.factura.bo/ExchangeRate/history?limit=5')
        self.assertLessEqual(urlopen.call_args.kwargs['timeout'], 10)
        self.assertEqual(guardadas, 1)
        self.assertEqual(TipoCambio.objects.get().fuente, 'Banco Central de Bolivia')

    def test_fallo_de_red_se_registra_y_conserva_la_ultima_cotizacion(self):
        TipoCambio.objects.create(fecha=date(2026, 11, 18), usd_bob=Decimal('11.75'), fuente='BCB')

        with mock.patch(CONSULTA, side_effect=urllib.error.URLError('sin red')), self.assertLogs(level='ERROR'):
            resultado = actualizar_tipo_cambio()

        self.assertIsNone(resultado)
        self.assertEqual(TipoCambio.objects.count(), 1)

    def test_respuesta_con_formato_roto_no_guarda_nada(self):
        with mock.patch(CONSULTA, return_value={'ok': False}), self.assertLogs(level='ERROR'):
            self.assertIsNone(actualizar_tipo_cambio())
        self.assertEqual(TipoCambio.objects.count(), 0)

    def test_json_invalido_se_trata_como_fallo(self):
        respuesta = mock.MagicMock()
        respuesta.__enter__.return_value = respuesta
        respuesta.read.return_value = b'<html>502</html>'
        with mock.patch('urllib.request.urlopen', return_value=respuesta), self.assertLogs(level='ERROR'):
            self.assertIsNone(actualizar_tipo_cambio())

    def test_comando_con_historial(self):
        datos = sobre(*(item((date(2026, 11, 19) - timedelta(days=d)).isoformat()) for d in range(3)))
        with mock.patch(CONSULTA, return_value=datos) as consulta:
            call_command('actualizar_tipo_cambio', '--historial', '3', stdout=mock.MagicMock())

        consulta.assert_called_once_with(3)
        self.assertEqual(TipoCambio.objects.count(), 3)


class TipoCambioVigenteTests(TestCase):
    def test_none_sin_cotizaciones(self):
        self.assertIsNone(tipo_cambio_vigente())

    def test_es_la_ultima_con_fecha_hasta_hoy(self):
        TipoCambio.objects.create(fecha=hoy() - timedelta(days=3), usd_bob=Decimal('11.60'), fuente='BCB')
        reciente = TipoCambio.objects.create(fecha=hoy() - timedelta(days=1), usd_bob=Decimal('11.70'), fuente='BCB')
        TipoCambio.objects.create(fecha=hoy() + timedelta(days=2), usd_bob=Decimal('99.00'), fuente='BCB')

        self.assertEqual(tipo_cambio_vigente(), reciente)


class TipoCambioApiTests(APITestCase):
    def test_publico_devuelve_vigente_e_historial(self):
        for dias in range(40):
            TipoCambio.objects.create(
                fecha=hoy() - timedelta(days=dias), usd_bob=Decimal('11.50') + Decimal(dias) / 100, fuente='BCB')

        r = self.client.get('/api/finanzas/tipo-cambio/')

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['vigente']['fecha'], hoy().isoformat())
        self.assertEqual(r.data['vigente']['usd_bob'], '11.5000')
        self.assertEqual(len(r.data['historial']), 30)

    def test_publico_sin_cotizacion(self):
        r = self.client.get('/api/finanzas/tipo-cambio/')

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, {'vigente': None, 'historial': []})

    def test_publico_ignora_un_token_vencido(self):
        r = self.client.get('/api/finanzas/tipo-cambio/', HTTP_AUTHORIZATION='Bearer vencido')

        self.assertEqual(r.status_code, 200)


URL_CRON = '/api/finanzas/tipo-cambio/actualizar/'


class CronTipoCambioTests(APITestCase):
    @override_settings(CRON_SECRET='')
    def test_sin_secreto_configurado_responde_503(self):
        self.assertEqual(self.client.get(URL_CRON, HTTP_AUTHORIZATION='Bearer ').status_code, 503)

    @override_settings(CRON_SECRET='s3creto')
    def test_sin_token_o_con_token_ajeno_responde_401(self):
        with mock.patch(CONSULTA) as consulta:
            self.assertEqual(self.client.get(URL_CRON).status_code, 401)
            self.assertEqual(self.client.get(URL_CRON, HTTP_AUTHORIZATION='Bearer otro').status_code, 401)
            self.assertEqual(self.client.get(URL_CRON, HTTP_AUTHORIZATION='s3creto').status_code, 401)
        consulta.assert_not_called()

    @override_settings(CRON_SECRET='s3creto')
    def test_con_token_correcto_actualiza(self):
        with mock.patch(CONSULTA, return_value=sobre(item(hoy().isoformat()))):
            r = self.client.get(URL_CRON, HTTP_AUTHORIZATION='Bearer s3creto')

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['guardadas'], 1)
        self.assertEqual(r.data['vigente']['usd_bob'], '11.6800')

    @override_settings(CRON_SECRET='s3creto')
    def test_si_la_api_externa_falla_responde_502(self):
        with mock.patch(CONSULTA, side_effect=TimeoutError()), self.assertLogs(level='ERROR'):
            r = self.client.get(URL_CRON, HTTP_AUTHORIZATION='Bearer s3creto')

        self.assertEqual(r.status_code, 502)


class BaseEmpresas(APITestCase):
    def setUp(self):
        rol_cliente = Rol.objects.get_or_create(nombre='cliente')[0]
        rol_empresa = Rol.objects.get_or_create(nombre='empresa')[0]
        self.cliente = Usuario.objects.create_user(
            email='cliente-fin@example.com', password='Password123!', rol=rol_cliente)
        self.empresa = Usuario.objects.create_user(
            email='empresa-fin@example.com', password='Password123!', rol=rol_empresa)
        self.otra_empresa = Usuario.objects.create_user(
            email='otra-empresa-fin@example.com', password='Password123!', rol=rol_empresa)
        self.tienda = Tienda.objects.create(propietario=self.empresa, nombre='Tienda Fin', slug='tienda-fin')
        self.tienda_ajena = Tienda.objects.create(
            propietario=self.otra_empresa, nombre='Tienda Ajena', slug='tienda-ajena')


class GastosTests(BaseEmpresas):
    def url(self, tienda=None, sufijo=''):
        return f'/api/finanzas/tiendas/{(tienda or self.tienda).id}/gastos/{sufijo}'

    def crear(self, **datos):
        cuerpo = {'categoria': 'alquiler', 'descripcion': 'Local', 'monto': '1500.00', 'fecha': '2026-11-05', **datos}
        self.client.force_authenticate(self.empresa)
        return self.client.post(self.url(), cuerpo, format='json')

    def test_alta_registra_tienda_y_usuario(self):
        r = self.crear()

        self.assertEqual(r.status_code, 201)
        gasto = GastoOperativo.objects.get()
        self.assertEqual((gasto.tienda, gasto.registrado_por), (self.tienda, self.empresa))
        self.assertEqual(r.data['categoria_etiqueta'], 'Alquiler')

    def test_alta_rechaza_monto_no_positivo_y_categoria_invalida(self):
        self.assertEqual(self.crear(monto='0').status_code, 400)
        self.assertEqual(self.crear(monto='-5').status_code, 400)
        self.assertEqual(self.crear(categoria='viajes').status_code, 400)
        self.assertEqual(GastoOperativo.objects.count(), 0)

    def test_lista_con_filtros(self):
        self.crear(fecha='2026-10-20', categoria='sueldos', monto='3000')
        self.crear(fecha='2026-11-05')
        self.crear(fecha='2026-11-20', categoria='servicios', monto='200')

        todos = self.client.get(self.url())
        noviembre = self.client.get(self.url(), {'desde': '2026-11-01', 'hasta': '2026-11-30'})
        servicios = self.client.get(self.url(), {'categoria': 'servicios'})

        self.assertEqual([g['fecha'] for g in todos.data], ['2026-11-20', '2026-11-05', '2026-10-20'])
        self.assertEqual(len(noviembre.data), 2)
        self.assertEqual([g['monto'] for g in servicios.data], ['200.00'])

    def test_filtros_invalidos_responden_400(self):
        self.client.force_authenticate(self.empresa)

        self.assertEqual(self.client.get(self.url(), {'desde': 'ayer'}).status_code, 400)
        self.assertEqual(self.client.get(self.url(), {'categoria': 'viajes'}).status_code, 400)
        self.assertEqual(
            self.client.get(self.url(), {'desde': '2026-12-01', 'hasta': '2026-11-01'}).status_code, 400)

    def test_totales_por_categoria_y_por_mes(self):
        self.crear(fecha='2026-10-20', categoria='sueldos', monto='3000')
        self.crear(fecha='2026-11-05', categoria='alquiler', monto='1500')
        self.crear(fecha='2026-11-20', categoria='alquiler', monto='500.50')

        r = self.client.get(self.url(sufijo='totales/'))

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['total'], Decimal('5000.50'))
        self.assertEqual(
            [(c['categoria'], c['total']) for c in r.data['por_categoria']],
            [('alquiler', Decimal('2000.50')), ('sueldos', Decimal('3000.00'))],
        )
        self.assertEqual(
            [(m['mes'], m['total']) for m in r.data['por_mes']],
            [('2026-10', Decimal('3000.00')), ('2026-11', Decimal('2000.50'))],
        )

    def test_totales_respetan_los_filtros_y_sin_gastos_dan_cero(self):
        self.crear(fecha='2026-10-20', monto='3000')

        r = self.client.get(self.url(sufijo='totales/'), {'desde': '2026-11-01'})

        self.assertEqual(r.data, {'total': Decimal('0.00'), 'por_categoria': [], 'por_mes': []})

    def test_edicion_y_borrado(self):
        gasto_id = self.crear().data['id']

        editado = self.client.patch(self.url(sufijo=f'{gasto_id}/'), {'monto': '1800'}, format='json')
        borrado = self.client.delete(self.url(sufijo=f'{gasto_id}/'))

        self.assertEqual((editado.status_code, editado.data['monto']), (200, '1800.00'))
        self.assertEqual(borrado.status_code, 204)
        self.assertEqual(GastoOperativo.objects.count(), 0)

    def test_otra_empresa_no_ve_ni_toca_los_gastos(self):
        gasto_id = self.crear().data['id']
        self.client.force_authenticate(self.otra_empresa)

        self.assertEqual(self.client.get(self.url()).status_code, 404)
        self.assertEqual(self.client.get(self.url(sufijo='totales/')).status_code, 404)
        self.assertEqual(self.client.post(self.url(), {
            'categoria': 'otros', 'monto': '10', 'fecha': '2026-11-05'}, format='json').status_code, 404)
        self.assertEqual(self.client.patch(
            self.url(sufijo=f'{gasto_id}/'), {'monto': '1'}, format='json').status_code, 404)
        self.assertEqual(self.client.delete(self.url(sufijo=f'{gasto_id}/')).status_code, 404)
        self.assertEqual(GastoOperativo.objects.get().monto, Decimal('1500.00'))

    def test_un_gasto_de_otra_tienda_propia_no_se_cuela_en_la_url(self):
        gasto_ajeno = GastoOperativo.objects.create(
            tienda=self.tienda_ajena, categoria='otros', monto=Decimal('9'), fecha=date(2026, 11, 1))
        self.client.force_authenticate(self.empresa)

        r = self.client.get(self.url(sufijo=f'{gasto_ajeno.id}/'))

        self.assertEqual(r.status_code, 404)

    def test_cliente_recibe_403_y_anonimo_401(self):
        self.client.force_authenticate(self.cliente)
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.assertEqual(self.client.post(self.url(), {
            'categoria': 'otros', 'monto': '10', 'fecha': '2026-11-05'}, format='json').status_code, 403)

        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url()).status_code, 401)


class StripeConTipoCambioTests(BaseEmpresas):
    def setUp(self):
        super().setUp()
        producto = Producto.objects.create(tienda=self.tienda, nombre='Producto', slug='producto-fin')
        self.variante = Variante.objects.create(
            producto=producto, nombre='Unica', sku='FIN-1', precio=Decimal('116.80'),
            costo_unitario=Decimal('80.00'), stock=10)
        carrito = Carrito.objects.create(cliente=self.cliente, tienda=self.tienda)
        ItemCarrito.objects.create(carrito=carrito, tienda=self.tienda, variante=self.variante, cantidad=1)

    def intento_creado(self):
        creado = SimpleNamespace(id='pi_fin', client_secret='cs_fin')
        self.client.force_authenticate(self.cliente)
        with mock.patch('stripe.PaymentIntent.create', return_value=creado) as crear:
            r = self.client.post('/api/pedidos/carrito/pago-intento/')
        return r, crear.call_args.kwargs

    def intento_stripe(self, centavos, tasa):
        return stripe.PaymentIntent.construct_from({
            'id': 'pi_fin',
            'object': 'payment_intent',
            'status': 'succeeded',
            'amount': centavos,
            'metadata': {'cliente_id': str(self.cliente.id), 'tipo_cambio_usd': str(tasa)},
        }, 'sk_test_dummy')

    def comprar(self, **cuerpo):
        self.client.force_authenticate(self.cliente)
        return self.client.post('/api/pedidos/carrito/checkout/', cuerpo, format='json')

    @override_settings(STRIPE_SECRET_KEY='sk_test_dummy', STRIPE_USD_BOB_RATE=10.99)
    def test_el_cobro_usa_la_cotizacion_vigente_y_no_la_tasa_fija(self):
        TipoCambio.objects.create(fecha=hoy(), usd_bob=Decimal('11.6800'), fuente='BCB')

        r, kwargs = self.intento_creado()

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['monto_usd'], '10.00')
        self.assertEqual(kwargs['amount'], 1000)
        self.assertEqual(kwargs['metadata']['tipo_cambio_usd'], '11.6800')

    @override_settings(STRIPE_SECRET_KEY='sk_test_dummy', STRIPE_USD_BOB_RATE=10.99)
    def test_sin_cotizacion_guardada_usa_la_tasa_fija(self):
        r, kwargs = self.intento_creado()

        self.assertEqual(r.data['monto_usd'], '10.63')
        self.assertEqual(kwargs['metadata']['tipo_cambio_usd'], '10.9900')

    @override_settings(STRIPE_SECRET_KEY='sk_test_dummy')
    def test_redondeo_half_up_a_centavos(self):
        TipoCambio.objects.create(fecha=hoy(), usd_bob=Decimal('11.7000'), fuente='BCB')
        self.variante.precio = Decimal('0.18')
        self.variante.save()

        r, _ = self.intento_creado()

        # 0.18 / 11.70 = 0.015384... -> 0.02
        self.assertEqual(r.data['monto_usd'], '0.02')

    @override_settings(STRIPE_SECRET_KEY='sk_test_dummy', STRIPE_USD_BOB_RATE=10.99)
    def test_checkout_guarda_la_tasa_cobrada_aunque_la_cotizacion_cambie(self):
        TipoCambio.objects.create(fecha=hoy() - timedelta(days=1), usd_bob=Decimal('11.6800'), fuente='BCB')
        # Entre el intento (a 11.68) y el checkout aparece la cotización nueva.
        TipoCambio.objects.create(fecha=hoy(), usd_bob=Decimal('11.9000'), fuente='BCB')

        with mock.patch(
            'stripe.PaymentIntent.retrieve', return_value=self.intento_stripe(1000, Decimal('11.6800'))
        ):
            r = self.comprar(metodo_pago='stripe', payment_intent_id='pi_fin')

        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(Pedido.objects.get().tipo_cambio_usd, Decimal('11.6800'))

    @override_settings(STRIPE_SECRET_KEY='sk_test_dummy', STRIPE_USD_BOB_RATE=10.99)
    def test_checkout_rechaza_un_cobro_que_no_cuadra_con_su_tasa(self):
        TipoCambio.objects.create(fecha=hoy(), usd_bob=Decimal('11.6800'), fuente='BCB')

        with mock.patch(
            'stripe.PaymentIntent.retrieve', return_value=self.intento_stripe(900, Decimal('11.6800'))
        ), mock.patch('stripe.Refund.create'):
            r = self.comprar(metodo_pago='stripe', payment_intent_id='pi_fin')

        self.assertEqual(r.status_code, 400)
        self.assertEqual(Pedido.objects.count(), 0)

    def test_pedido_en_efectivo_guarda_la_cotizacion_vigente_o_nada(self):
        self.assertEqual(self.comprar(metodo_pago='efectivo').status_code, 201)
        self.assertIsNone(Pedido.objects.get().tipo_cambio_usd)

        TipoCambio.objects.create(fecha=hoy(), usd_bob=Decimal('11.6800'), fuente='BCB')
        carrito = Carrito.objects.get(cliente=self.cliente)
        ItemCarrito.objects.create(carrito=carrito, tienda=self.tienda, variante=self.variante, cantidad=1)
        self.assertEqual(self.comprar(metodo_pago='efectivo').status_code, 201)

        self.assertEqual(Pedido.objects.latest('id').tipo_cambio_usd, Decimal('11.6800'))

    def test_el_pedido_del_cliente_expone_la_tasa_pero_no_el_costo(self):
        TipoCambio.objects.create(fecha=hoy(), usd_bob=Decimal('11.6800'), fuente='BCB')
        self.comprar(metodo_pago='efectivo')
        pedido = Pedido.objects.get()
        self.client.force_authenticate(self.cliente)

        lista = self.client.get('/api/pedidos/mis-pedidos/')
        detalle = self.client.get(f'/api/pedidos/mis-pedidos/{pedido.id}/')

        self.assertEqual(lista.data['pedidos'][0]['tipo_cambio_usd'], '11.6800')
        self.assertEqual(detalle.data['tipo_cambio_usd'], '11.6800')


class CostoUnitarioTests(BaseEmpresas):
    def setUp(self):
        super().setUp()
        self.producto = Producto.objects.create(tienda=self.tienda, nombre='Producto', slug='producto-costo')
        self.variante = Variante.objects.create(
            producto=self.producto, nombre='Unica', sku='COSTO-1', precio=Decimal('100.00'),
            costo_unitario=Decimal('60.00'), stock=5)
        carrito = Carrito.objects.create(cliente=self.cliente, tienda=self.tienda)
        ItemCarrito.objects.create(carrito=carrito, tienda=self.tienda, variante=self.variante, cantidad=1)

    def test_las_vistas_publicas_y_de_cliente_nunca_exponen_el_costo(self):
        self.client.force_authenticate(self.cliente)
        self.client.post('/api/pedidos/carrito/checkout/', {'metodo_pago': 'efectivo'}, format='json')
        ItemCarrito.objects.create(
            carrito=Carrito.objects.get(cliente=self.cliente), tienda=self.tienda,
            variante=self.variante, cantidad=1)
        pedido = Pedido.objects.get()

        urls = [
            '/api/catalogo/tiendas/',
            '/api/catalogo/productos/',
            f'/api/catalogo/productos/{self.producto.id}/',
            f'/api/catalogo/tiendas/{self.tienda.id}/productos/',
            '/api/pedidos/carrito/',
            '/api/pedidos/mis-pedidos/',
            f'/api/pedidos/mis-pedidos/{pedido.id}/',
        ]
        for url in urls:
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 200)
                self.assertNotIn('costo_unitario', r.content.decode())

    def test_la_empresa_ve_y_edita_el_costo(self):
        self.client.force_authenticate(self.empresa)
        base = f'/api/tiendas/{self.tienda.id}/productos/'

        lista = self.client.get(base)
        editado = self.client.patch(
            f'{base}{self.producto.id}/', {'costo_unitario': '65.50'}, format='json')

        self.assertEqual(lista.data[0]['variantes'][0]['costo_unitario'], '60.00')
        self.assertEqual(editado.status_code, 200)
        self.assertEqual(editado.data['variantes'][0]['costo_unitario'], '65.50')
        self.variante.refresh_from_db()
        self.assertEqual(self.variante.costo_unitario, Decimal('65.50'))

    def test_costo_negativo_se_rechaza_y_null_lo_borra(self):
        self.client.force_authenticate(self.empresa)
        url = f'/api/tiendas/{self.tienda.id}/productos/{self.producto.id}/'

        self.assertEqual(self.client.patch(url, {'costo_unitario': '-1'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'costo_unitario': None}, format='json').status_code, 200)
        self.variante.refresh_from_db()
        self.assertIsNone(self.variante.costo_unitario)

    def test_editar_otros_campos_no_toca_el_costo(self):
        self.client.force_authenticate(self.empresa)

        self.client.patch(
            f'/api/tiendas/{self.tienda.id}/productos/{self.producto.id}/', {'nombre': 'Nuevo'}, format='json')

        self.variante.refresh_from_db()
        self.assertEqual(self.variante.costo_unitario, Decimal('60.00'))


class PrecioUsdTests(BaseEmpresas):
    def setUp(self):
        super().setUp()
        self.producto = Producto.objects.create(tienda=self.tienda, nombre='Teclado', slug='teclado')
        self.variante = Variante.objects.create(
            producto=self.producto, nombre='Unica', sku='TEC-1', precio=Decimal('100.00'),
            costo_unitario=Decimal('60.00'), stock=5)
        self.base = f'/api/tiendas/{self.tienda.id}/productos/'
        self.client.force_authenticate(self.empresa)

    def cargar_cotizacion(self, usd='11.7500', fecha=None):
        return TipoCambio.objects.create(fecha=fecha or hoy(), usd_bob=Decimal(usd))

    def crear(self, **variante):
        datos = {
            'nombre': 'Mouse',
            'descripcion': 'Mouse inalámbrico',
            'variantes': json.dumps([{'sku': 'MOU-1', 'stock': 3, 'stock_minimo': 1, **variante}]),
            'imagenes': [SimpleUploadedFile('a.jpg', b'x', content_type='image/jpeg')],
        }
        with mock.patch(
            'apps.catalogo.services.upload_product_image', return_value={'url': 'u', 'public_id': 'p'},
        ):
            return self.client.post(self.base, datos, format='multipart')

    def fijar_en_dolares(self, usd='25.00', bs='293.75'):
        self.variante.precio_usd = Decimal(usd)
        self.variante.precio = Decimal(bs)
        self.variante.save()

    def test_crear_en_dolares_calcula_el_precio_en_bs_con_la_cotizacion_vigente(self):
        self.cargar_cotizacion('11.7500')

        r = self.crear(precio_usd='25.00')

        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['variantes'][0]['precio_usd'], '25.00')
        self.assertEqual(r.data['variantes'][0]['precio'], '293.75')
        self.assertEqual(r.data['precio_usd'], '25.00')

    def test_el_redondeo_es_half_up_a_centavos(self):
        self.cargar_cotizacion('11.6850')

        r = self.crear(precio_usd='0.10')

        # 0.10 * 11.6850 = 1.1685 -> 1.17
        self.assertEqual(r.data['variantes'][0]['precio'], '1.17')

    def test_crear_en_dolares_sin_cotizacion_responde_400_claro(self):
        r = self.crear(precio_usd='25.00')

        self.assertEqual(r.status_code, 400)
        self.assertIn('No hay tipo de cambio oficial cargado', str(r.data))
        self.assertFalse(Variante.objects.filter(sku='MOU-1').exists())

    def test_crear_sin_precio_ni_precio_usd_responde_400(self):
        self.cargar_cotizacion()

        self.assertEqual(self.crear().status_code, 400)

    def test_crear_en_bs_no_guarda_precio_usd(self):
        r = self.crear(precio='80.00')

        self.assertEqual(r.status_code, 201, r.data)
        self.assertIsNone(r.data['variantes'][0]['precio_usd'])
        self.assertIsNone(r.data['precio_usd'])

    def test_editar_a_dolares_recalcula_el_precio_en_bs(self):
        self.cargar_cotizacion('11.7500')

        r = self.client.patch(f'{self.base}{self.producto.id}/', {'precio_usd': '25.00'}, format='json')

        self.assertEqual(r.status_code, 200, r.data)
        self.variante.refresh_from_db()
        self.assertEqual(self.variante.precio_usd, Decimal('25.00'))
        self.assertEqual(self.variante.precio, Decimal('293.75'))
        self.assertEqual(r.data['precio'], '293.75')
        self.assertEqual(r.data['precio_usd'], '25.00')

    def test_editar_a_dolares_sin_cotizacion_responde_400_y_no_cambia_nada(self):
        r = self.client.patch(f'{self.base}{self.producto.id}/', {'precio_usd': '25.00'}, format='json')

        self.assertEqual(r.status_code, 400)
        self.assertIn('No hay tipo de cambio oficial cargado', str(r.data))
        self.variante.refresh_from_db()
        self.assertIsNone(self.variante.precio_usd)
        self.assertEqual(self.variante.precio, Decimal('100.00'))

    def test_precio_usd_null_devuelve_el_producto_a_precio_fijo_en_bs(self):
        self.cargar_cotizacion('11.7500')
        url = f'{self.base}{self.producto.id}/'
        self.client.patch(url, {'precio_usd': '25.00'}, format='json')

        r = self.client.patch(url, {'precio_usd': None}, format='json')

        self.assertEqual(r.status_code, 200, r.data)
        self.variante.refresh_from_db()
        self.assertIsNone(self.variante.precio_usd)
        self.assertEqual(self.variante.precio, Decimal('293.75'))

    def test_precio_usd_no_positivo_se_rechaza(self):
        self.cargar_cotizacion()

        r = self.client.patch(f'{self.base}{self.producto.id}/', {'precio_usd': '0'}, format='json')

        self.assertEqual(r.status_code, 400)

    def test_un_precio_en_bs_saca_al_producto_de_dolares(self):
        self.cargar_cotizacion('11.7500')
        url = f'{self.base}{self.producto.id}/'
        self.client.patch(url, {'precio_usd': '25.00'}, format='json')

        self.client.patch(url, {'precio': '300.00'}, format='json')

        self.variante.refresh_from_db()
        self.assertIsNone(self.variante.precio_usd)
        self.assertEqual(self.variante.precio, Decimal('300.00'))

    def test_una_cotizacion_nueva_recalcula_solo_los_productos_en_dolares(self):
        self.fijar_en_dolares()
        fijo = Variante.objects.create(
            producto=self.producto, nombre='Fija', sku='TEC-2', precio=Decimal('100.00'), stock=1)
        self.cargar_cotizacion('11.7500', fecha=hoy() - timedelta(days=1))

        with mock.patch(CONSULTA, return_value=sobre(item(hoy().isoformat(), usd=11.9))):
            actualizar_tipo_cambio()

        self.variante.refresh_from_db()
        fijo.refresh_from_db()
        self.assertEqual(self.variante.precio, Decimal('297.50'))
        self.assertEqual(fijo.precio, Decimal('100.00'))

    def test_si_la_api_falla_los_precios_en_bs_no_se_tocan(self):
        self.fijar_en_dolares()

        with mock.patch(CONSULTA, side_effect=TimeoutError()), self.assertLogs(level='ERROR'):
            actualizar_tipo_cambio()

        self.variante.refresh_from_db()
        self.assertEqual(self.variante.precio, Decimal('293.75'))

    def test_precio_usd_es_publico_y_el_costo_nunca(self):
        self.fijar_en_dolares()
        self.client.force_authenticate(None)

        for url in (
            '/api/catalogo/productos/',
            f'/api/catalogo/productos/{self.producto.id}/',
            f'/api/catalogo/tiendas/{self.tienda.id}/productos/',
        ):
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 200)
                self.assertIn('"precio_usd":"25.00"', r.content.decode())
                self.assertNotIn('costo_unitario', r.content.decode())

    def test_precio_base_usd_es_el_de_la_variante_mas_barata(self):
        self.fijar_en_dolares()
        self.client.force_authenticate(None)

        r = self.client.get(f'/api/catalogo/productos/{self.producto.id}/')

        self.assertEqual(r.data['precio_base'], '293.75')
        self.assertEqual(r.data['precio_base_usd'], '25.00')

        Variante.objects.create(
            producto=self.producto, nombre='Barata', sku='TEC-3', precio=Decimal('50.00'), stock=1)
        r = self.client.get(f'/api/catalogo/productos/{self.producto.id}/')

        self.assertEqual(r.data['precio_base'], '50.00')
        self.assertIsNone(r.data['precio_base_usd'])
