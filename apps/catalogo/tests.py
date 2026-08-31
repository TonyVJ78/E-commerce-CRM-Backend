from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.tiendas.models import Tienda
from apps.usuarios.models import Rol, Usuario

from .models import Producto, VarianteProducto


class CatalogoClienteAPITests(APITestCase):
    def setUp(self):
        rol_cliente = Rol.objects.get(nombre='cliente')
        rol_empresa = Rol.objects.get(nombre='empresa')
        self.cliente = Usuario.objects.create_user(
            email='cliente-catalogo@example.com',
            password='Password123!',
            rol=rol_cliente,
        )
        self.empresa = Usuario.objects.create_user(
            email='empresa-catalogo@example.com',
            password='Password123!',
            rol=rol_empresa,
        )
        self.tienda_uno = Tienda.objects.create(
            propietario=self.empresa,
            nombre='Tienda Uno',
            slug='tienda-uno',
        )
        self.tienda_dos = Tienda.objects.create(
            propietario=self.empresa,
            nombre='Tienda Dos',
            slug='tienda-dos',
        )
        self.producto_uno = Producto.objects.create(
            tienda=self.tienda_uno,
            nombre='Producto Uno',
            precio_base=Decimal('10.00'),
        )
        Producto.objects.create(
            tienda=self.tienda_dos,
            nombre='Producto Dos',
            precio_base=Decimal('20.00'),
        )
        self.variante_uno = VarianteProducto.objects.create(
            tienda=self.tienda_uno,
            producto=self.producto_uno,
            nombre_variante='Variante Uno',
            precio_adicional=Decimal('2.00'),
        )
        # El esquema permite esta inconsistencia; el endpoint no debe exponerla
        # como variante de la tienda uno.
        VarianteProducto.objects.create(
            tienda=self.tienda_dos,
            producto=self.producto_uno,
            nombre_variante='Variante de otro tenant',
            precio_adicional=Decimal('3.00'),
        )

    def test_cliente_lista_tiendas_sin_datos_privados_del_propietario(self):
        self.client.force_authenticate(user=self.cliente)

        response = self.client.get(reverse('catalogo_tiendas'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertNotIn('propietario', response.data[0])
        self.assertNotIn('propietario_email', response.data[0])

    def test_productos_y_variantes_quedan_aislados_por_tienda(self):
        self.client.force_authenticate(user=self.cliente)

        response = self.client.get(
            reverse('catalogo_productos_tienda', args=[self.tienda_uno.id])
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.producto_uno.id)
        self.assertEqual(len(response.data[0]['variantes']), 1)
        self.assertEqual(
            response.data[0]['variantes'][0]['id'],
            self.variante_uno.id,
        )

    def test_usuario_no_cliente_no_accede_al_catalogo(self):
        self.client.force_authenticate(user=self.empresa)

        response = self.client.get(reverse('catalogo_tiendas'))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
