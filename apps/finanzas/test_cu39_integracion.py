"""Regresiones CU-39 con datos sintéticos; Stripe/Cloudinary/proveedor simulados."""
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import stripe
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.utils import timezone

from apps.catalogo.models import Categoria, Producto, Variante
from apps.pedidos.models import Carrito, ItemCarrito, Pedido, Pago
from apps.usuarios.models import LogAuditoria
from apps.marketing.models import Cupon
from .admin import TipoCambioAdmin
from .models import TipoCambio
from .tipo_cambio import actualizar_tipo_cambio, parsear_historial, RespuestaInvalida
from .tests import BaseEmpresas


class SeguridadYVariantesTests(BaseEmpresas):
    def setUp(self):
        super().setUp()
        self.producto = Producto.objects.create(tienda=self.tienda, nombre='Producto original', slug='original')
        self.uno = Variante.objects.create(producto=self.producto, nombre='Uno', sku='U1', precio=100, stock=10)
        self.dos = Variante.objects.create(producto=self.producto, nombre='Dos', sku='U2', precio=200, stock=10)
        ajeno = Producto.objects.create(tienda=self.tienda_ajena, nombre='Ajeno', slug='ajeno')
        self.ajena = Variante.objects.create(producto=ajeno, nombre='Ajena', sku='A1', precio=300, stock=10)
        self.categoria_ajena = Categoria.objects.create(tienda=self.tienda_ajena, nombre='Privada')
        self.url = f'/api/tiendas/{self.tienda.id}/productos/{self.producto.id}/'
        self.client.force_authenticate(self.empresa)

    def patch(self, **data):
        return self.client.patch(self.url, data, format='json')

    def test_costo_de_variante_elegida_conserva_precios_y_otra_variante(self):
        self.uno.costo_unitario = Decimal('30.00')
        self.uno.save(update_fields=['costo_unitario'])
        self.dos.costo_unitario = Decimal('20.00')
        self.dos.save(update_fields=['costo_unitario'])
        r = self.patch(variante_id=self.dos.pk, costo_unitario='25.00')
        self.assertEqual(r.status_code, 200)
        self.uno.refresh_from_db()
        self.dos.refresh_from_db()
        self.assertEqual((self.uno.precio, self.uno.costo_unitario), (Decimal('100'), Decimal('30')))
        self.assertEqual((self.dos.precio, self.dos.costo_unitario), (Decimal('200'), Decimal('25')))

    def test_no_permite_trasladar_producto_a_tienda_ajena(self):
        r = self.patch(tienda=self.tienda_ajena.id, nombre='Intrusión')
        self.assertEqual(r.status_code, 400)
        self.producto.refresh_from_db()
        self.assertEqual((self.producto.tienda_id, self.producto.nombre), (self.tienda.id, 'Producto original'))

    def test_categoria_id_de_otra_tienda_es_rechazada(self):
        self.assertEqual(self.patch(categoria_id=self.categoria_ajena.id).status_code, 400)
        self.producto.refresh_from_db()
        self.assertIsNone(self.producto.categoria_id)

    def test_categoria_legacy_de_otra_tienda_es_rechazada(self):
        self.assertEqual(self.patch(categoria=self.categoria_ajena.id).status_code, 400)

    def test_categoria_de_otra_tienda_del_mismo_propietario_es_rechazada(self):
        from apps.tiendas.models import Tienda
        propia = Tienda.objects.create(propietario=self.empresa, nombre='Segunda', slug='segunda')
        cat = Categoria.objects.create(tienda=propia, nombre='Otra')
        self.assertEqual(self.patch(categoria_id=cat.id).status_code, 400)

    def test_variante_de_otra_empresa_es_rechazada(self):
        self.assertEqual(self.patch(variante_id=self.ajena.id, precio='1.00').status_code, 400)
        self.ajena.refresh_from_db()
        self.assertEqual(self.ajena.precio, Decimal('300.00'))

    def test_variante_de_otro_producto_propio_es_rechazada(self):
        otro = Producto.objects.create(tienda=self.tienda, nombre='Otro', slug='otro')
        var = Variante.objects.create(producto=otro, sku='O1', precio=50, stock=1)
        self.assertEqual(self.patch(variante_id=var.id, precio='1.00').status_code, 400)

    def test_edita_variante_elegida_sin_cambiar_primera(self):
        TipoCambio.objects.create(fecha=timezone.localdate(), usd_bob='8.1250', fuente='Fixture')
        r = self.patch(variante_id=self.dos.id, precio_usd='12.00')
        self.assertEqual(r.status_code, 200, r.data)
        self.uno.refresh_from_db(); self.dos.refresh_from_db()
        self.assertEqual(self.uno.precio, Decimal('100.00'))
        self.assertEqual((self.dos.precio, self.dos.precio_usd), (Decimal('97.50'), Decimal('12.00')))

    def test_preserva_edicion_legacy_de_primera_variante(self):
        self.assertEqual(self.patch(precio='70.12').status_code, 200)
        self.uno.refresh_from_db(); self.dos.refresh_from_db()
        self.assertEqual((self.uno.precio, self.dos.precio), (Decimal('70.12'), Decimal('200.00')))

    def test_importes_bs_invalidos_no_modifican_producto_ni_variante(self):
        for value in ['-0.01', None, 'NaN', 'Infinity', '1.001', '10000000000.00', {'x': 1}, True]:
            with self.subTest(value=value):
                r = self.patch(precio=value, nombre='No debe guardarse')
                self.assertEqual(r.status_code, 400, r.data)
                self.uno.refresh_from_db(); self.producto.refresh_from_db()
                self.assertEqual(self.uno.precio, Decimal('100.00'))
                self.assertEqual(self.producto.nombre, 'Producto original')

    def test_precio_usd_convertido_fuera_de_rango_es_rechazado(self):
        TipoCambio.objects.create(fecha=timezone.localdate(), usd_bob='20.0000')
        self.assertEqual(self.patch(precio_usd='9999999999.99', nombre='No guardar').status_code, 400)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.nombre, 'Producto original')

    def test_error_al_guardar_variante_revierte_nombre_y_categoria(self):
        with mock.patch.object(Variante, 'save', side_effect=ValidationError('Fallo simulado')):
            with self.assertRaises(ValidationError):
                self.patch(nombre='Revertir', categoria='Temporal', precio='55.00')
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.nombre, 'Producto original')
        self.assertFalse(Categoria.objects.filter(tienda=self.tienda, nombre='Temporal').exists())

    def test_cliente_anonimo_y_empresa_ajena_no_editan(self):
        for user, expected in [(None, 401), (self.cliente, 403), (self.otra_empresa, 404)]:
            with self.subTest(expected=expected):
                self.client.force_authenticate(user)
                self.assertEqual(self.patch(precio='1.00').status_code, expected)

    def test_registra_cambio_monetario_en_auditoria(self):
        self.assertEqual(self.patch(variante_id=self.dos.id, precio='140.25').status_code, 200)
        log = LogAuditoria.objects.filter(tabla_afectada='producto', registro_id=self.producto.id).latest('id')
        self.assertEqual(log.usuario_id, self.empresa.id)
        self.assertEqual(log.datos_nuevos['variantes'][1]['precio'], '140.25')


@override_settings(STRIPE_SECRET_KEY='sk_test_dummy', STRIPE_USD_BOB_RATE=8)
class OfertaCheckoutHistoricoTests(BaseEmpresas):
    def setUp(self):
        super().setUp()
        self.producto = Producto.objects.create(tienda=self.tienda, nombre='Oferta', slug='oferta')
        self.variante = Variante.objects.create(producto=self.producto, sku='OF1', precio=100, precio_oferta=80, stock=20)
        self.carrito = Carrito.objects.create(cliente=self.cliente, tienda=self.tienda)
        ItemCarrito.objects.create(tienda=self.tienda, carrito=self.carrito, variante=self.variante, cantidad=2)
        self.client.force_authenticate(self.cliente)
        TipoCambio.objects.create(fecha=timezone.localdate(), usd_bob='8.0000', fuente='Fixture sintética')

    def iniciar(self, **data):
        with mock.patch('stripe.PaymentIntent.create', return_value=SimpleNamespace(id='pi_cu39', client_secret='cs_fixture')) as create:
            response = self.client.post('/api/pedidos/carrito/pago-intento/', data, format='json')
        return response, create.call_args.kwargs

    def confirmar(self, kwargs, **data):
        intent = stripe.PaymentIntent.construct_from({'id': 'pi_cu39', 'status': 'succeeded',
            'currency': kwargs['currency'], 'amount': kwargs['amount'], 'metadata': kwargs['metadata']}, 'sk_test_dummy')
        with mock.patch('stripe.PaymentIntent.retrieve', return_value=intent):
            return self.client.post('/api/pedidos/carrito/checkout/', {'metodo_pago': 'stripe', 'payment_intent_id': 'pi_cu39', **data}, format='json')

    def test_oferta_es_precio_efectivo_en_carrito_stripe_y_pedido(self):
        carrito = self.client.get('/api/pedidos/carrito/')
        self.assertEqual(Decimal(str(carrito.data['total_global'])), Decimal('160.00'))
        r, kwargs = self.iniciar()
        self.assertEqual((r.status_code, kwargs['amount'], r.data['tipo_cambio_usd']), (200, 2000, '8.0000'))
        compra = self.confirmar(kwargs)
        self.assertEqual(compra.status_code, 201, compra.data)
        pedido = Pedido.objects.get()
        self.assertEqual((pedido.total, pedido.items.get().precio_unitario, Pago.objects.get().monto),
            (Decimal('160.00'), Decimal('80.00'), Decimal('160.00')))

    def test_catalogo_publica_el_mismo_precio_efectivo_que_la_compra(self):
        self.variante.precio_usd = Decimal('12.50')
        self.variante.save()
        r = self.client.get(f'/api/catalogo/productos/{self.producto.id}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['precio_base'], '80.00')
        self.assertIsNone(r.data['precio_base_usd'])

    def test_cupon_se_aplica_sobre_precio_efectivo_y_conserva_importe(self):
        hoy = timezone.localdate()
        Cupon.objects.create(tienda=self.tienda, codigo='CU39TEST', tipo_descuento='porcentaje', valor_descuento=10,
            fecha_inicio=hoy, fecha_expiracion=hoy+timedelta(days=1), usos_maximos=5, limite_por_cliente=1)
        codigos = {str(self.tienda.id): 'CU39TEST'}
        r, kwargs = self.iniciar(cupones=codigos)
        self.assertEqual((r.status_code, kwargs['amount']), (200, 1800))
        compra = self.confirmar(kwargs, cupones=codigos)
        self.assertEqual(compra.status_code, 201, compra.data)
        pedido = Pedido.objects.get()
        self.assertEqual((pedido.subtotal, pedido.total, Pago.objects.get().monto),
            (Decimal('160.00'), Decimal('144.00'), Decimal('144.00')))

    def test_moneda_stripe_distinta_es_rechazada(self):
        _, kwargs = self.iniciar()
        kwargs['currency'] = 'eur'
        self.assertEqual(self.confirmar(kwargs).status_code, 400)
        self.assertFalse(Pedido.objects.exists())

    def test_cambio_de_precio_tras_intento_no_crea_pedido_inconsistente(self):
        _, kwargs = self.iniciar()
        self.variante.precio_oferta = Decimal('90.00')
        self.variante.save()
        with mock.patch('stripe.Refund.create') as refund:
            self.assertEqual(self.confirmar(kwargs).status_code, 400)
            refund.assert_called_once()
        self.assertFalse(Pedido.objects.exists())

    def test_pedido_conserva_importes_y_tasa_tras_nueva_cotizacion(self):
        _, kwargs = self.iniciar()
        self.assertEqual(self.confirmar(kwargs).status_code, 201)
        pedido = Pedido.objects.get()
        self.variante.precio_usd = Decimal('12.50')
        self.variante.save()
        with mock.patch('apps.finanzas.tipo_cambio._consultar_historial', return_value={
            'ok': True, 'datos': [{'fecha': timezone.localdate().isoformat(), 'usd_bob': '9.0000'}]}):
            actualizar_tipo_cambio()
        pedido.refresh_from_db()
        self.variante.refresh_from_db()
        self.assertEqual(self.variante.precio, Decimal('112.50'))
        self.assertEqual((pedido.total, pedido.tipo_cambio_usd, pedido.items.get().precio_unitario),
            (Decimal('160.00'), Decimal('8.0000'), Decimal('80.00')))


class ActualizacionAtomicaTests(BaseEmpresas):
    def test_fallo_de_recalculo_revierte_historial(self):
        fecha = timezone.localdate()
        payload = {'ok': True, 'datos': [{'fecha': fecha.isoformat(), 'usd_bob': '8.0000'}]}
        with mock.patch('apps.finanzas.tipo_cambio._consultar_historial', return_value=payload), \
             mock.patch('apps.finanzas.tipo_cambio.recalcular_precios_usd', side_effect=RuntimeError('Simulado')):
            with self.assertRaises(RuntimeError):
                actualizar_tipo_cambio()
        self.assertFalse(TipoCambio.objects.exists())
        self.assertFalse(LogAuditoria.objects.filter(tabla_afectada='tipo_cambio').exists())

    def test_admin_recalcula_precios_con_tasa_guardada(self):
        producto = Producto.objects.create(tienda=self.tienda, nombre='USD', slug='usd')
        variante = Variante.objects.create(producto=producto, sku='D1', precio=70, precio_usd=10, stock=1)
        cambio = TipoCambio(fecha=timezone.localdate(), usd_bob=Decimal('8.5000'), fuente='Fixture')
        TipoCambioAdmin(TipoCambio, AdminSite()).save_model(SimpleNamespace(user=self.empresa), cambio, None, False)
        variante.refresh_from_db()
        self.assertEqual(variante.precio, Decimal('85.00'))

    def test_actualizacion_de_cotizacion_registra_auditoria(self):
        payload = {'ok': True, 'datos': [{'fecha': timezone.localdate().isoformat(), 'usd_bob': '8.0000'}]}
        with mock.patch('apps.finanzas.tipo_cambio._consultar_historial', return_value=payload):
            actualizar_tipo_cambio()
            actualizar_tipo_cambio()
        self.assertEqual(LogAuditoria.objects.filter(tabla_afectada='tipo_cambio').count(), 1)

    def test_cambio_que_desborda_precio_revierte_y_conserva_tasa_anterior(self):
        fecha = timezone.localdate()
        TipoCambio.objects.create(fecha=fecha, usd_bob='1.0000', fuente='Fixture')
        producto = Producto.objects.create(tienda=self.tienda, nombre='Límite', slug='limite')
        variante = Variante.objects.create(producto=producto, sku='L1', precio='9000000000.00', precio_usd='9000000000.00', stock=1)
        payload = {'ok': True, 'datos': [{'fecha': fecha.isoformat(), 'usd_bob': '2.0000'}]}
        with mock.patch('apps.finanzas.tipo_cambio._consultar_historial', return_value=payload):
            self.assertIsNone(actualizar_tipo_cambio())
        variante.refresh_from_db()
        self.assertEqual(variante.precio, Decimal('9000000000.00'))
        self.assertEqual(TipoCambio.objects.get().usd_bob, Decimal('1.0000'))

    def test_cotizaciones_no_representables_se_rechazan(self):
        for tasa in ['0.000001', '1000000.0000', 'NaN', 'Infinity']:
            with self.subTest(tasa=tasa):
                with self.assertRaises(RespuestaInvalida):
                    parsear_historial({'ok': True, 'datos': [{'fecha': '2026-01-01', 'usd_bob': tasa}]})
