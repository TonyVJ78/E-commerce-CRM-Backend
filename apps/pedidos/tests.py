from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalogo.models import Producto, Variante
from apps.tiendas.models import Tienda
from apps.usuarios.models import Rol, Usuario

from .models import Carrito, ItemCarrito


class AgregarItemCarritoAPITests(APITestCase):
    def setUp(self):
        rol_cliente = Rol.objects.get_or_create(nombre='cliente')[0]
        rol_empresa = Rol.objects.get_or_create(nombre='empresa')[0]
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
            slug='producto-uno',
        )
        self.producto_dos = Producto.objects.create(
            tienda=self.tienda_dos,
            nombre='Producto Dos',
            slug='producto-dos',
        )
        self.variante_uno = Variante.objects.create(
            producto=self.producto_uno,
            nombre='Variante Uno',
            sku='VAR-UNO-C',
            precio=Decimal('15.00'),
            stock=10,
        )
        self.variante_dos = Variante.objects.create(
            producto=self.producto_dos,
            nombre='Variante Dos',
            sku='VAR-DOS-C',
            precio=Decimal('25.00'),
            stock=5,
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
