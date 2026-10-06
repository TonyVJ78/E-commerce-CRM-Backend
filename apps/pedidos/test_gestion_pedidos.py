"""Pruebas de CU-22 (gestión de pedidos recibidos de tienda)."""

from decimal import Decimal

from rest_framework.test import APITestCase

from apps.catalogo.models import Producto, Variante
from apps.tiendas.models import Tienda
from apps.usuarios.models import Rol, Usuario

from .models import Carrito, DireccionEnvio, ItemCarrito, Pedido

PRECIO = Decimal('109.90')


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
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['conteos']['pendiente'], 1)
        self.assertEqual(r.data['pedidos'][0]['siguientes_estados'], ['procesado', 'cancelado'])

        self.assertEqual(self.cambiar(pedido, 'enviado').status_code, 409)  # no se puede saltar
        self.assertEqual(self.cambiar(pedido, 'procesado').status_code, 200)
        r = self.cambiar(pedido, 'enviado', transportista='Trans', numero_seguimiento='ABC')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['envio']['numero_seguimiento'], 'ABC')
        r = self.cambiar(pedido, 'entregado')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['pago']['estado'], 'pagado')
        self.assertEqual(
            [h['estado'] for h in r.data['historial']],
            ['pendiente', 'procesado', 'enviado', 'entregado'])
        self.assertEqual(self.cambiar(pedido, 'cancelado').status_code, 409)

        # El cliente ve el mismo estado e historial (CU-20)
        self.client.force_authenticate(self.cliente)
        visto = self.client.get('/api/pedidos/mis-pedidos/').data['pedidos'][0]
        self.assertEqual(visto['estado'], 'entregado')

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

    def test_aislamiento_entre_empresas_y_roles(self):
        pedido = self.crear_pedido()
        self.client.force_authenticate(self.otra_empresa)
        self.assertEqual(self.client.get(f'/api/tiendas/{self.tienda.id}/pedidos/').status_code, 404)
        self.assertEqual(self.cambiar(pedido, 'procesado').status_code, 404)

    def test_estado_invalido_y_filtros(self):
        pedido = self.crear_pedido()
        self.client.force_authenticate(self.empresa)

        self.assertEqual(self.cambiar(pedido, 'inexistente').status_code, 400)
        r = self.client.get(f'/api/tiendas/{self.tienda.id}/pedidos/?q={pedido.id}&estado=pendiente')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data['pedidos']), 1)

    def test_pedido_legado_completado_se_trata_como_pendiente(self):
        pedido = self.crear_pedido()
        Pedido.objects.filter(pk=pedido.pk).update(estado_actual='completado')
        self.client.force_authenticate(self.empresa)

        r = self.client.get(f'/api/tiendas/{self.tienda.id}/pedidos/?estado=pendiente')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['conteos']['pendiente'], 1)
