from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalogo.models import Producto, VarianteProducto
from apps.tiendas.models import Tienda
from apps.usuarios.models import Rol, Usuario

from .models import Carrito, ItemCarrito


class AgregarItemCarritoAPITests(APITestCase):
    def setUp(self):
        rol_cliente = Rol.objects.get(nombre='cliente')
        rol_empresa = Rol.objects.get(nombre='empresa')
        self.cliente = Usuario.objects.create_user(
            email='cliente-carrito@example.com',
            password='Password123!',
            rol=rol_cliente,
        )
        self.empresa = Usuario.objects.create_user(
            email='empresa-carrito@example.com',
            password='Password123!',
            rol=rol_empresa,
        )
        self.tienda_uno = Tienda.objects.create(
            propietario=self.empresa,
            nombre='Tienda Uno',
            slug='carrito-tienda-uno',
        )
        self.tienda_dos = Tienda.objects.create(
            propietario=self.empresa,
            nombre='Tienda Dos',
            slug='carrito-tienda-dos',
        )
        self.producto_uno = Producto.objects.create(
            tienda=self.tienda_uno,
            nombre='Producto Uno',
            precio_base=Decimal('15.00'),
        )
        self.producto_dos = Producto.objects.create(
            tienda=self.tienda_dos,
            nombre='Producto Dos',
            precio_base=Decimal('25.00'),
        )
        self.variante_uno = VarianteProducto.objects.create(
            tienda=self.tienda_uno,
            producto=self.producto_uno,
            nombre_variante='Variante Uno',
            precio_adicional=Decimal('1.00'),
        )
        self.variante_dos = VarianteProducto.objects.create(
            tienda=self.tienda_dos,
            producto=self.producto_dos,
            nombre_variante='Variante Dos',
            precio_adicional=Decimal('2.00'),
        )
        self.url = reverse('agregar_item_carrito')

    def payload(self, tienda=None, variante=None):
        return {
            'tienda_id': (tienda or self.tienda_uno).id,
            'variante_id': (variante or self.variante_uno).id,
        }

    def test_cliente_autorizado_agrega_item_con_tenant_consistente(self):
        self.client.force_authenticate(user=self.cliente)

        response = self.client.post(self.url, self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        item = ItemCarrito.objects.get(pk=response.data['id'])
        self.assertEqual(item.cantidad, 1)
        self.assertEqual(item.tienda_id, self.tienda_uno.id)
        self.assertEqual(item.carrito.tienda_id, self.tienda_uno.id)
        self.assertEqual(item.variante.tienda_id, self.tienda_uno.id)
        self.assertEqual(item.variante.producto.tienda_id, self.tienda_uno.id)
        self.assertEqual(response.data['producto_id'], self.producto_uno.id)

    def test_usuario_con_rol_no_cliente_recibe_403(self):
        self.client.force_authenticate(user=self.empresa)

        response = self.client.post(self.url, self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(ItemCarrito.objects.exists())

    def test_variante_de_otra_tienda_es_rechazada(self):
        self.client.force_authenticate(user=self.cliente)

        response = self.client.post(
            self.url,
            self.payload(tienda=self.tienda_uno, variante=self.variante_dos),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('variante_id', response.data)
        self.assertFalse(Carrito.objects.exists())
        self.assertFalse(ItemCarrito.objects.exists())

    def test_variante_cuyo_producto_es_de_otra_tienda_es_rechazada(self):
        variante_inconsistente = VarianteProducto.objects.create(
            tienda=self.tienda_uno,
            producto=self.producto_dos,
            nombre_variante='Variante con producto de otro tenant',
            precio_adicional=Decimal('3.00'),
        )
        self.client.force_authenticate(user=self.cliente)

        response = self.client.post(
            self.url,
            self.payload(tienda=self.tienda_uno, variante=variante_inconsistente),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('variante_id', response.data)
        self.assertFalse(Carrito.objects.exists())
        self.assertFalse(ItemCarrito.objects.exists())

    def test_crea_carrito_cuando_no_existe(self):
        self.client.force_authenticate(user=self.cliente)
        self.assertFalse(
            Carrito.objects.filter(cliente=self.cliente, tienda=self.tienda_uno).exists()
        )

        response = self.client.post(self.url, self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            Carrito.objects.filter(cliente=self.cliente, tienda=self.tienda_uno).count(),
            1,
        )

    def test_reutiliza_el_unico_carrito_existente(self):
        carrito = Carrito.objects.create(
            cliente=self.cliente,
            tienda=self.tienda_uno,
        )
        self.client.force_authenticate(user=self.cliente)

        response = self.client.post(self.url, self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['carrito_id'], carrito.id)
        self.assertEqual(
            Carrito.objects.filter(cliente=self.cliente, tienda=self.tienda_uno).count(),
            1,
        )

    def test_no_reutiliza_carrito_de_otra_tienda(self):
        carrito_otra_tienda = Carrito.objects.create(
            cliente=self.cliente,
            tienda=self.tienda_dos,
        )
        self.client.force_authenticate(user=self.cliente)

        response = self.client.post(self.url, self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(response.data['carrito_id'], carrito_otra_tienda.id)
        self.assertEqual(
            Carrito.objects.filter(cliente=self.cliente, tienda=self.tienda_uno).count(),
            1,
        )
        self.assertEqual(
            Carrito.objects.filter(cliente=self.cliente, tienda=self.tienda_dos).count(),
            1,
        )

    def test_varios_carritos_para_cliente_y_tienda_devuelven_409(self):
        Carrito.objects.create(cliente=self.cliente, tienda=self.tienda_uno)
        Carrito.objects.create(cliente=self.cliente, tienda=self.tienda_uno)
        self.client.force_authenticate(user=self.cliente)

        response = self.client.post(self.url, self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['detail'].code, 'multiples_carritos')
        self.assertFalse(ItemCarrito.objects.exists())

    def test_variante_repetida_crea_items_independientes_sin_incrementar(self):
        self.client.force_authenticate(user=self.cliente)

        primera_respuesta = self.client.post(self.url, self.payload(), format='json')
        segunda_respuesta = self.client.post(self.url, self.payload(), format='json')

        self.assertEqual(primera_respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(segunda_respuesta.status_code, status.HTTP_201_CREATED)
        items = ItemCarrito.objects.order_by('id')
        self.assertEqual(items.count(), 2)
        self.assertNotEqual(items[0].id, items[1].id)
        self.assertEqual(items[0].cantidad, 1)
        self.assertEqual(items[1].cantidad, 1)
