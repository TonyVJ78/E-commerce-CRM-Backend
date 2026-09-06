import json
from decimal import Decimal
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.tiendas.models import Tienda
from apps.usuarios.models import Rol, Usuario

from .models import Categoria, Producto, Variante
from .services import create_product_with_images


class ProductoApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa_rol = Rol.objects.get_or_create(nombre='empresa')[0]
        cls.cliente_rol = Rol.objects.get_or_create(nombre='cliente')[0]
        cls.empresa = Usuario.objects.create_user(
            email='empresa@test.local',
            password='Password123!',
            rol=cls.empresa_rol,
        )
        cls.cliente = Usuario.objects.create_user(
            email='cliente@test.local',
            password='Password123!',
            rol=cls.cliente_rol,
        )
        cls.otra_empresa = Usuario.objects.create_user(
            email='otra-empresa@test.local',
            password='Password123!',
            rol=cls.empresa_rol,
        )
        cls.tienda = Tienda.objects.create(
            propietario=cls.empresa,
            nombre='Tienda propia',
            slug='tienda-propia',
        )
        cls.otra_tienda = Tienda.objects.create(
            propietario=cls.otra_empresa,
            nombre='Tienda ajena',
            slug='tienda-ajena',
        )
        cls.categoria = Categoria.objects.create(
            tienda=cls.tienda,
            nombre='Ropa',
        )
        cls.otra_categoria = Categoria.objects.create(
            tienda=cls.otra_tienda,
            nombre='Ajena',
        )

    def _sample_image(self, name='test.jpg'):
        return SimpleUploadedFile(
            name=name,
            content=b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00',
            content_type='image/jpeg',
        )

    def _auth(self, user=None):
        self.client.force_authenticate(user=user or self.empresa)

    @patch('apps.catalogo.services.uploader.upload')
    def test_crear_producto_exitoso(self, mock_upload):
        mock_upload.side_effect = [
            {'secure_url': 'https://res.cloudinary.com/demo/image/upload/v1/p1.jpg'},
            {'secure_url': 'https://res.cloudinary.com/demo/image/upload/v1/p2.jpg'},
        ]
        self._auth()
        url = reverse('producto-list-create', kwargs={'tienda_id': self.tienda.id})
        data = {
            'nombre': 'Polera oversize',
            'descripcion': 'Polera de algodon peruano',
            'categoria_id': self.categoria.id,
            'etiquetas': json.dumps(['ropa', 'verano']),
            'variantes': json.dumps([
                {
                    'sku': 'POL-NEG-M',
                    'nombre': 'M / Negro',
                    'precio': '79.90',
                    'precio_oferta': '69.90',
                    'stock': 15,
                    'stock_minimo': 3,
                    'atributos': {'talla': 'M', 'color': 'Negro'},
                },
                {
                    'sku': 'POL-NEG-L',
                    'nombre': 'L / Negro',
                    'precio': '79.90',
                    'stock': 8,
                    'stock_minimo': 2,
                    'atributos': {'talla': 'L', 'color': 'Negro'},
                },
            ]),
            'imagenes': [self._sample_image('img1.jpg'), self._sample_image('img2.jpg')],
        }

        response = self.client.post(url, data, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['nombre'], 'Polera oversize')
        self.assertEqual(response.data['slug'], 'polera-oversize')
        self.assertEqual(len(response.data['imagenes']), 2)
        self.assertEqual(len(response.data['variantes']), 2)
        self.assertEqual(response.data['stock_total'], 23)
        self.assertTrue(response.data['en_stock'])
        self.assertFalse(response.data['agotado'])

    def test_crear_producto_sin_autenticacion_devuelve_401(self):
        url = reverse('producto-list-create', kwargs={'tienda_id': self.tienda.id})
        response = self.client.post(url, {}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_crear_producto_con_rol_no_empresa_devuelve_403(self):
        self._auth(self.cliente)
        url = reverse('producto-list-create', kwargs={'tienda_id': self.tienda.id})
        response = self.client.post(url, {}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_crear_producto_en_tienda_ajena_devuelve_404(self):
        self._auth()
        url = reverse('producto-list-create', kwargs={'tienda_id': self.otra_tienda.id})
        response = self.client.post(url, {}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_crear_producto_con_categoria_de_otra_tienda_devuelve_400(self):
        self._auth()
        url = reverse('producto-list-create', kwargs={'tienda_id': self.tienda.id})
        data = {
            'nombre': 'Polera invalida',
            'descripcion': 'Descripcion',
            'categoria_id': self.otra_categoria.id,
            'variantes': json.dumps([
                {
                    'sku': 'POL-INV-1',
                    'precio': '50.00',
                    'stock': 1,
                    'stock_minimo': 0,
                }
            ]),
            'imagenes': [self._sample_image('img1.jpg')],
        }
        response = self.client.post(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('categoria_id', response.data)

    def test_crear_producto_sin_imagenes_devuelve_400(self):
        self._auth()
        url = reverse('producto-list-create', kwargs={'tienda_id': self.tienda.id})
        data = {
            'nombre': 'Polera sin imagen',
            'descripcion': 'Descripcion',
            'variantes': json.dumps([
                {
                    'sku': 'POL-SIN-1',
                    'precio': '50.00',
                    'stock': 1,
                    'stock_minimo': 0,
                }
            ]),
        }
        response = self.client.post(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('imagenes', response.data)

    def test_crear_producto_con_skus_duplicados_en_payload_devuelve_400(self):
        self._auth()
        url = reverse('producto-list-create', kwargs={'tienda_id': self.tienda.id})
        data = {
            'nombre': 'Polera skus duplicados',
            'descripcion': 'Descripcion',
            'variantes': json.dumps([
                {'sku': 'SKU-DUP', 'precio': '50.00', 'stock': 1, 'stock_minimo': 0},
                {'sku': 'sku-dup', 'precio': '50.00', 'stock': 1, 'stock_minimo': 0},
            ]),
            'imagenes': [self._sample_image('img1.jpg')],
        }
        response = self.client.post(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('variantes', response.data)

    @patch('apps.catalogo.services.uploader.upload')
    def test_crear_producto_con_sku_existente_en_otra_tienda_es_permitido(self, mock_upload):
        mock_upload.side_effect = [
            {'secure_url': 'https://res.cloudinary.com/demo/image/upload/v1/p1.jpg'},
            {'secure_url': 'https://res.cloudinary.com/demo/image/upload/v1/p2.jpg'},
        ]
        self._auth(self.otra_empresa)
        url_otra = reverse('producto-list-create', kwargs={'tienda_id': self.otra_tienda.id})
        payload_otra = {
            'nombre': 'Producto ajeno',
            'descripcion': 'Desc',
            'variantes': json.dumps([
                {'sku': 'SKU-COMPARTIDO', 'precio': '10.00', 'stock': 2, 'stock_minimo': 1}
            ]),
            'imagenes': [self._sample_image('img_otra.jpg')],
        }
        resp_otra = self.client.post(url_otra, payload_otra, format='multipart')
        self.assertEqual(resp_otra.status_code, status.HTTP_201_CREATED)

        self._auth(self.empresa)
        url_propia = reverse('producto-list-create', kwargs={'tienda_id': self.tienda.id})
        payload_propia = {
            'nombre': 'Producto propio',
            'descripcion': 'Desc',
            'variantes': json.dumps([
                {'sku': 'SKU-COMPARTIDO', 'precio': '20.00', 'stock': 3, 'stock_minimo': 1}
            ]),
            'imagenes': [self._sample_image('img_propia.jpg')],
        }
        resp_propia = self.client.post(url_propia, payload_propia, format='multipart')
        self.assertEqual(resp_propia.status_code, status.HTTP_201_CREATED)

    @patch('apps.catalogo.services.uploader.upload')
    def test_crear_producto_con_sku_existente_en_misma_tienda_lanza_error(self, mock_upload):
        mock_upload.side_effect = [
            {'secure_url': 'https://res.cloudinary.com/demo/image/upload/v1/p1.jpg'},
            {'secure_url': 'https://res.cloudinary.com/demo/image/upload/v1/p2.jpg'},
        ]
        self._auth()
        url = reverse('producto-list-create', kwargs={'tienda_id': self.tienda.id})
        payload1 = {
            'nombre': 'Producto 1',
            'descripcion': 'Desc',
            'variantes': json.dumps([
                {'sku': 'SKU-MISMA-TIENDA', 'precio': '10.00', 'stock': 2, 'stock_minimo': 1}
            ]),
            'imagenes': [self._sample_image('img1.jpg')],
        }
        resp1 = self.client.post(url, payload1, format='multipart')
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED)

        payload2 = {
            'nombre': 'Producto 2',
            'descripcion': 'Desc',
            'variantes': json.dumps([
                {'sku': 'SKU-MISMA-TIENDA', 'precio': '20.00', 'stock': 3, 'stock_minimo': 1}
            ]),
            'imagenes': [self._sample_image('img2.jpg')],
        }
        resp2 = self.client.post(url, payload2, format='multipart')
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('apps.catalogo.services.uploader.upload')
    def test_rollback_si_falla_guardado(self, mock_upload):
        mock_upload.return_value = {'secure_url': 'https://res.cloudinary.com/demo/image/upload/v1/p1.jpg'}
        total_productos_antes = Producto.objects.count()
        total_variantes_antes = Variante.objects.count()

        validated_data = {
            'nombre': 'Producto rollback',
            'descripcion': 'Desc',
            'activo': True,
            'etiquetas': [],
            'categoria_id': None,
            'variantes': [
                {'sku': 'SKU-OK', 'nombre': 'V1', 'precio': Decimal('10.00'), 'stock': 1, 'stock_minimo': 0, 'atributos': {}, 'activa': True},
            ],
            'imagenes': [self._sample_image('ok.jpg')],
        }

        with patch('apps.catalogo.services.Variante.objects.bulk_create', side_effect=IntegrityError('Error simulado')):
            with self.assertRaises(IntegrityError):
                create_product_with_images(tienda=self.tienda, validated_data=validated_data)

        self.assertEqual(Producto.objects.count(), total_productos_antes)
        self.assertEqual(Variante.objects.count(), total_variantes_antes)


class CatalogoClienteAPITests(APITestCase):
    def setUp(self):
        rol_cliente = Rol.objects.get_or_create(nombre='cliente')[0]
        rol_empresa = Rol.objects.get_or_create(nombre='empresa')[0]
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
            slug='producto-uno',
        )
        Producto.objects.create(
            tienda=self.tienda_dos,
            nombre='Producto Dos',
            slug='producto-dos',
        )
        self.variante_uno = Variante.objects.create(
            producto=self.producto_uno,
            nombre='Variante Uno',
            sku='VAR-UNO',
            precio=Decimal('12.00'),
            stock=10,
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
