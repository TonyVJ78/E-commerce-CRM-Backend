"""Pruebas de CU-19 (checkout / pago con Stripe) y CU-22 (gestión de pedidos).

Stripe se simula con `mock`: no se hace ninguna llamada de red. Requieren
PostgreSQL porque el stock, los totales y el historial viven en triggers.
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.catalogo.models import Producto, Variante
from apps.tiendas.models import Tienda
from apps.usuarios.models import Rol, Usuario

from .models import Carrito, DireccionEnvio, ItemCarrito, Pago, Pedido

PRECIO = Decimal('109.90')  # con la tasa 10.99 → 10.00 USD por unidad


def intento(centavos, cliente_id, status='succeeded', pi_id='pi_test_1'):
    return SimpleNamespace(
        id=pi_id,
        status=status,
        amount=centavos,
        metadata={'cliente_id': str(cliente_id)},
        client_secret='cs_test',
    )


@override_settings(STRIPE_SECRET_KEY='sk_test_dummy', STRIPE_USD_BOB_RATE=10.99)
class BaseCompra(APITestCase):
    def setUp(self):
        rol_cliente = Rol.objects.get_or_create(nombre='cliente')[0]
        rol_empresa = Rol.objects.get_or_create(nombre='empresa')[0]
        self.cliente = Usuario.objects.create_user(
            email='cliente-pago@example.com', password='Password123!', rol=rol_cliente)
        self.otro_cliente = Usuario.objects.create_user(
            email='otro-pago@example.com', password='Password123!', rol=rol_cliente)
        self.empresa = Usuario.objects.create_user(
            email='empresa-pago@example.com', password='Password123!', rol=rol_empresa)
        self.otra_empresa = Usuario.objects.create_user(
            email='otra-empresa-pago@example.com', password='Password123!', rol=rol_empresa)
        self.tienda = Tienda.objects.create(
            propietario=self.empresa, nombre='Tienda Pago', slug='tienda-pago')
        producto = Producto.objects.create(tienda=self.tienda, nombre='Producto', slug='producto-pago')
        self.variante = Variante.objects.create(
            producto=producto, nombre='Unica', sku='PAGO-1', precio=PRECIO, stock=10)

    def llenar_carrito(self, cantidad=2):
        carrito, _ = Carrito.objects.get_or_create(cliente=self.cliente, tienda=self.tienda)
        ItemCarrito.objects.create(
            carrito=carrito, tienda=self.tienda, variante=self.variante, cantidad=cantidad)

    def comprar(self, **cuerpo):
        self.client.force_authenticate(self.cliente)
        return self.client.post('/api/pedidos/carrito/checkout/', cuerpo, format='json')

    def stock(self):
        self.variante.refresh_from_db()
        return self.variante.stock


class CheckoutTests(BaseCompra):
    def test_efectivo_crea_pedido_pendiente_y_descuenta_stock(self):
        self.llenar_carrito()

        r = self.comprar(metodo_pago='efectivo')

        self.assertEqual(r.status_code, 201)
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.estado_actual, 'pendiente')
        self.assertEqual(pedido.total, Decimal('219.80'))
        self.assertEqual(self.stock(), 8)
        self.assertEqual(Pago.objects.get().estado, 'pendiente')
        self.assertEqual(
            list(pedido.historial_estados.values_list('estado', flat=True)), ['pendiente'])

    def test_stripe_aprobado_registra_pago_pagado(self):
        self.llenar_carrito()
        with mock.patch('stripe.PaymentIntent.retrieve', return_value=intento(2000, self.cliente.id)):
            r = self.comprar(metodo_pago='stripe', payment_intent_id='pi_test_1')

        self.assertEqual(r.status_code, 201)
        pago = Pago.objects.get()
        self.assertEqual((pago.estado, pago.referencia_transaccion), ('pagado', 'pi_test_1'))

    def test_stripe_no_completado_es_rechazado(self):
        self.llenar_carrito()
        retorno = intento(2000, self.cliente.id, status='requires_payment_method')
        with mock.patch('stripe.PaymentIntent.retrieve', return_value=retorno):
            r = self.comprar(metodo_pago='stripe', payment_intent_id='pi_test_1')

        self.assertEqual(r.status_code, 400)
        self.assertEqual(Pedido.objects.count(), 0)

    def test_stripe_sin_payment_intent_es_rechazado(self):
        self.llenar_carrito()
        self.assertEqual(self.comprar(metodo_pago='stripe').status_code, 400)

    def test_payment_intent_no_se_puede_reutilizar(self):
        self.llenar_carrito()
        with mock.patch('stripe.PaymentIntent.retrieve', return_value=intento(2000, self.cliente.id)):
            self.assertEqual(
                self.comprar(metodo_pago='stripe', payment_intent_id='pi_test_1').status_code, 201)
            self.llenar_carrito()
            r = self.comprar(metodo_pago='stripe', payment_intent_id='pi_test_1')

        self.assertEqual(r.status_code, 409)
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(ItemCarrito.objects.count(), 1)  # el segundo carrito sigue intacto

    def test_payment_intent_de_otro_cliente_es_rechazado_sin_reembolso(self):
        self.llenar_carrito()
        ajeno = intento(2000, self.otro_cliente.id)
        with mock.patch('stripe.PaymentIntent.retrieve', return_value=ajeno), \
                mock.patch('stripe.Refund.create') as reembolso:
            r = self.comprar(metodo_pago='stripe', payment_intent_id='pi_test_1')

        self.assertEqual(r.status_code, 403)
        reembolso.assert_not_called()
        self.assertEqual(Pedido.objects.count(), 0)

    def test_monto_distinto_reembolsa_el_pago(self):
        self.llenar_carrito()
        with mock.patch('stripe.PaymentIntent.retrieve', return_value=intento(500, self.cliente.id)), \
                mock.patch('stripe.Refund.create') as reembolso:
            r = self.comprar(metodo_pago='stripe', payment_intent_id='pi_test_1')

        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.data['reembolsado'])
        reembolso.assert_called_once_with(payment_intent='pi_test_1')
        self.assertEqual(Pedido.objects.count(), 0)

    def test_sin_stock_reembolsa_y_no_deja_pedido(self):
        self.llenar_carrito(cantidad=50)
        cobrado = intento(round(float(PRECIO) * 50 / 10.99 * 100), self.cliente.id)
        with mock.patch('stripe.PaymentIntent.retrieve', return_value=cobrado), \
                mock.patch('stripe.Refund.create') as reembolso:
            r = self.comprar(metodo_pago='stripe', payment_intent_id='pi_test_1')

        self.assertEqual(r.status_code, 400)
        self.assertIn('Stock insuficiente', r.data['error'])
        self.assertTrue(r.data['reembolsado'])
        reembolso.assert_called_once()
        self.assertEqual((Pedido.objects.count(), self.stock()), (0, 10))

    def test_efectivo_sin_stock_no_intenta_reembolsar(self):
        self.llenar_carrito(cantidad=50)
        with mock.patch('stripe.Refund.create') as reembolso:
            r = self.comprar(metodo_pago='efectivo')

        self.assertEqual(r.status_code, 400)
        self.assertNotIn('reembolsado', r.data)
        reembolso.assert_not_called()

    def test_checkout_con_carrito_vacio(self):
        self.assertEqual(self.comprar(metodo_pago='efectivo').status_code, 400)


class PagoIntentoTests(BaseCompra):
    def test_carrito_vacio(self):
        self.client.force_authenticate(self.cliente)
        self.assertEqual(self.client.post('/api/pedidos/carrito/pago-intento/').status_code, 400)

    def test_no_cobra_si_falta_stock(self):
        self.llenar_carrito(cantidad=50)
        self.client.force_authenticate(self.cliente)
        with mock.patch('stripe.PaymentIntent.create') as crear:
            r = self.client.post('/api/pedidos/carrito/pago-intento/')

        self.assertEqual(r.status_code, 400)
        self.assertIn('No hay stock suficiente', r.data['error'])
        crear.assert_not_called()

    def test_crea_el_intento_en_dolares_con_metadata_del_cliente(self):
        self.llenar_carrito()
        self.client.force_authenticate(self.cliente)
        creado = SimpleNamespace(id='pi_nuevo', client_secret='cs_nuevo')
        with mock.patch('stripe.PaymentIntent.create', return_value=creado) as crear:
            r = self.client.post('/api/pedidos/carrito/pago-intento/')

        self.assertEqual(r.status_code, 200)
        kwargs = crear.call_args.kwargs
        self.assertEqual((kwargs['amount'], kwargs['currency']), (2000, 'usd'))
        self.assertEqual(kwargs['metadata']['cliente_id'], str(self.cliente.id))
        self.assertEqual(r.data['monto_usd'], '20.00')


class GestionPedidosTests(BaseCompra):
    def crear_pedido(self):
        self.llenar_carrito()
        self.comprar(metodo_pago='efectivo')
        return Pedido.objects.get()

    def url(self, pedido, sufijo='', tienda=None):
        return f'/api/tiendas/{(tienda or self.tienda).id}/pedidos/{pedido.id}/{sufijo}'

    def cambiar(self, pedido, estado, **extra):
        return self.client.patch(
            self.url(pedido, 'estado/'), {'estado': estado, **extra}, format='json')

    def test_ciclo_completo_hasta_entregado(self):
        pedido = self.crear_pedido()
        DireccionEnvio.objects.create(
            tienda=self.tienda, cliente=self.cliente, direccion='Calle 1', ciudad='La Paz')
        self.client.force_authenticate(self.empresa)

        r = self.client.get(f'/api/tiendas/{self.tienda.id}/pedidos/')
        self.assertEqual(r.data['conteos']['pendiente'], 1)
        self.assertEqual(r.data['pedidos'][0]['siguientes_estados'], ['procesado', 'cancelado'])

        self.assertEqual(self.cambiar(pedido, 'enviado').status_code, 409)  # no se puede saltar
        self.assertEqual(self.cambiar(pedido, 'procesado').status_code, 200)
        r = self.cambiar(pedido, 'enviado', transportista='Trans', numero_seguimiento='ABC')
        self.assertEqual(r.data['envio']['numero_seguimiento'], 'ABC')
        r = self.cambiar(pedido, 'entregado')
        self.assertEqual(r.data['pago']['estado'], 'pagado')
        self.assertEqual(
            [h['estado'] for h in r.data['historial']],
            ['pendiente', 'procesado', 'enviado', 'entregado'])
        self.assertEqual(self.cambiar(pedido, 'cancelado').status_code, 409)

        # El cliente ve el mismo estado e historial (CU-20)
        self.client.force_authenticate(self.cliente)
        visto = self.client.get('/api/pedidos/mis-pedidos/').data['pedidos'][0]
        self.assertEqual(visto['estado'], 'entregado')
        self.assertEqual(visto['metodo_pago'], 'Efectivo')
        self.assertEqual(visto['envio']['transportista'], 'Trans')

    def test_enviado_sin_direccion_avisa_y_no_crea_envio(self):
        pedido = self.crear_pedido()
        self.client.force_authenticate(self.empresa)
        self.cambiar(pedido, 'procesado')

        r = self.cambiar(pedido, 'enviado')

        self.assertEqual(r.status_code, 200)
        self.assertIn('dirección de envío', r.data['aviso'])
        self.assertIsNone(r.data['envio'])

    def test_cancelar_devuelve_stock_y_anula_pago_pendiente(self):
        pedido = self.crear_pedido()
        self.assertEqual(self.stock(), 8)
        self.client.force_authenticate(self.empresa)

        r = self.cambiar(pedido, 'cancelado')

        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.stock(), 10)
        self.assertEqual(r.data['pago']['estado'], 'anulado')

    def test_cancelar_pedido_pagado_con_tarjeta_avisa_del_reembolso(self):
        self.llenar_carrito()
        with mock.patch('stripe.PaymentIntent.retrieve', return_value=intento(2000, self.cliente.id)):
            self.comprar(metodo_pago='stripe', payment_intent_id='pi_test_1')
        self.client.force_authenticate(self.empresa)

        r = self.cambiar(Pedido.objects.get(), 'cancelado')

        self.assertIn('reembolso', r.data['aviso'])

    def test_aislamiento_entre_empresas_y_roles(self):
        pedido = self.crear_pedido()
        self.client.force_authenticate(self.otra_empresa)
        self.assertEqual(self.client.get(f'/api/tiendas/{self.tienda.id}/pedidos/').status_code, 404)
        self.assertEqual(self.cambiar(pedido, 'procesado').status_code, 404)
        self.assertEqual(Pedido.objects.get().estado_actual, 'pendiente')

        tienda_ajena = Tienda.objects.create(
            propietario=self.otra_empresa, nombre='Ajena', slug='tienda-ajena')
        self.assertEqual(self.client.get(self.url(pedido, tienda=tienda_ajena)).status_code, 404)

        self.client.force_authenticate(self.cliente)
        self.assertEqual(self.client.get(f'/api/tiendas/{self.tienda.id}/pedidos/').status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f'/api/tiendas/{self.tienda.id}/pedidos/').status_code, 401)

    def test_estado_invalido_y_filtros(self):
        pedido = self.crear_pedido()
        self.client.force_authenticate(self.empresa)

        self.assertEqual(self.cambiar(pedido, 'inexistente').status_code, 400)
        r = self.client.get(f'/api/tiendas/{self.tienda.id}/pedidos/?q={pedido.id}&estado=pendiente')
        self.assertEqual(len(r.data['pedidos']), 1)
        r = self.client.get(f'/api/tiendas/{self.tienda.id}/pedidos/?estado=entregado')
        self.assertEqual(len(r.data['pedidos']), 0)

    def test_pedido_legado_completado_se_trata_como_pendiente(self):
        pedido = self.crear_pedido()
        Pedido.objects.filter(pk=pedido.pk).update(estado_actual='completado')
        self.client.force_authenticate(self.empresa)

        r = self.client.get(f'/api/tiendas/{self.tienda.id}/pedidos/?estado=pendiente')

        self.assertEqual(r.data['pedidos'][0]['estado'], 'pendiente')
        self.assertEqual(self.cambiar(pedido, 'procesado').status_code, 200)
