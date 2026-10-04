from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalogo.models import Producto, Variante
from apps.tiendas.models import Tienda
from apps.usuarios.models import Rol, Usuario

from .models import (
    Carrito,
    HistorialEstadoPedido,
    ItemCarrito,
    ItemPedido,
    Pedido,
    Resena,
)


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


class CasosUsoPedidosClienteAPITests(APITestCase):
    def setUp(self):
        rol_cliente = Rol.objects.get_or_create(nombre='cliente')[0]
        rol_empresa = Rol.objects.get_or_create(nombre='empresa')[0]
        self.cliente = Usuario.objects.create_user(
            email='cliente-seguimiento@example.com', password='Password123!', rol=rol_cliente,
        )
        self.otro_cliente = Usuario.objects.create_user(
            email='otro-seguimiento@example.com', password='Password123!', rol=rol_cliente,
        )
        empresa = Usuario.objects.create_user(
            email='empresa-seguimiento@example.com', password='Password123!', rol=rol_empresa,
        )
        self.tienda = Tienda.objects.create(
            propietario=empresa, nombre='Tienda Seguimiento', slug='tienda-seguimiento',
        )
        self.producto = Producto.objects.create(
            tienda=self.tienda, nombre='Producto Seguimiento', slug='producto-seguimiento',
        )
        self.variante = Variante.objects.create(
            producto=self.producto,
            nombre='Unidad',
            sku='TRACK-001',
            precio=Decimal('12.50'),
            stock=5,
        )
        self.pedido = Pedido.objects.create(
            cliente=self.cliente,
            tienda=self.tienda,
            estado_actual='entregado',
            subtotal=Decimal('12.50'),
            total=Decimal('12.50'),
        )
        ItemPedido.objects.create(
            tienda=self.tienda,
            pedido=self.pedido,
            variante=self.variante,
            cantidad=1,
            precio_unitario=Decimal('12.50'),
        )
        HistorialEstadoPedido.objects.create(
            tienda=self.tienda,
            pedido=self.pedido,
            estado='pendiente',
            observacion='Recibido',
        )
        self.detalle_url = reverse('pedido_detalle_cliente', args=[self.pedido.pk])
        self.resenas_url = reverse('resenas_pedido', args=[self.pedido.pk])

    def test_detalle_muestra_historial_en_orden_y_observacion(self):
        self.client.force_authenticate(user=self.cliente)

        response = self.client.get(self.detalle_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items'][0]['producto_id'], self.producto.pk)
        self.assertIn('Recibido', [entrada['observacion'] for entrada in response.data['historial']])
        self.assertLessEqual(response.data['historial'][0]['fecha'], response.data['historial'][-1]['fecha'])

    def test_pedido_de_otro_cliente_no_se_expone(self):
        self.client.force_authenticate(user=self.otro_cliente)

        response = self.client.get(self.detalle_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cliente_puede_calificar_producto_comprado_y_tienda(self):
        self.client.force_authenticate(user=self.cliente)
        producto_response = self.client.post(self.resenas_url, {
            'tipo': 'producto',
            'producto_id': self.producto.pk,
            'calificacion': 5,
            'comentario': 'Muy bueno',
        }, format='json')
        tienda_response = self.client.post(self.resenas_url, {
            'tipo': 'tienda',
            'calificacion': 4,
            'comentario': 'Buena atención',
        }, format='json')

        self.assertEqual(producto_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(tienda_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Resena.objects.count(), 2)
        self.assertIsNone(Resena.objects.get(producto__isnull=True).producto_id)

    def test_no_permite_calificar_producto_no_comprado_ni_puntuacion_invalida(self):
        otro_producto = Producto.objects.create(
            tienda=self.tienda,
            nombre='Otro Producto',
            slug='otro-producto-seguimiento',
        )
        self.client.force_authenticate(user=self.cliente)

        producto_response = self.client.post(self.resenas_url, {
            'tipo': 'producto',
            'producto_id': otro_producto.pk,
            'calificacion': 4,
        }, format='json')
        puntuacion_response = self.client.post(self.resenas_url, {
            'tipo': 'tienda',
            'calificacion': 6,
        }, format='json')

        self.assertEqual(producto_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(puntuacion_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Resena.objects.exists())

    def test_no_permite_resenar_pedido_no_completado(self):
        self.pedido.estado_actual = 'pendiente'
        self.pedido.save(update_fields=['estado_actual'])
        self.client.force_authenticate(user=self.cliente)

        response = self.client.post(self.resenas_url, {
            'tipo': 'tienda',
            'calificacion': 4,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Resena.objects.exists())
