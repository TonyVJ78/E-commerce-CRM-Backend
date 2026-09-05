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
        cls.empresa_rol = Rol.objects.create(nombre='empresa')
        cls.cliente_rol = Rol.objects.create(nombre='cliente')
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

    def product_url(self, tienda_id=None):
        return reverse(
            'producto-list-create',
            kwargs={'tienda_id': tienda_id or self.tienda.id},
        )

    def valid_payload(self, **overrides):
        payload = {
            'nombre': 'Polera Kantu',
            'descripcion': 'Producto artesanal de prueba',
            'categoria_id': str(self.categoria.id),
            'etiquetas': json.dumps(['artesanal', 'ropa']),
            'activo': 'true',
            'variantes': json.dumps([{
                'sku': 'POL-RO-M',
                'nombre': 'Rojo / M',
                'precio': '120.00',
                'precio_oferta': '99.90',
                'stock': 10,
                'stock_minimo': 3,
                'atributos': {'color': 'Rojo', 'talla': 'M'},
                'activa': True,
            }]),
            'imagenes': SimpleUploadedFile(
                'producto.png',
                b'\x89PNG\r\n\x1a\ncontenido',
                content_type='image/png',
            ),
        }
        payload.update(overrides)
        return payload

    def test_requires_authentication(self):
        response = self.client.get(self.product_url())
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rejects_non_empresa(self):
        self.client.force_authenticate(self.cliente)
        response = self.client.get(self.product_url())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('apps.catalogo.services.upload_product_image')
    def test_owner_can_create_product_and_calculates_stock(self, upload):
        upload.return_value = {
            'url': 'https://res.cloudinary.com/demo/producto.png',
            'public_id': 'kantu/test/producto',
        }
        self.client.force_authenticate(self.empresa)

        response = self.client.post(
            self.product_url(),
            self.valid_payload(),
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['stock_total'], 10)
        self.assertFalse(response.data['agotado'])
        self.assertTrue(response.data['en_stock'])
        self.assertEqual(Producto.objects.count(), 1)
        variante = Variante.objects.get()
        self.assertEqual(variante.precio, Decimal('120.00'))
        self.assertEqual(variante.sku, 'POL-RO-M')
        upload.assert_called_once()

    def test_rejects_foreign_store(self):
        self.client.force_authenticate(self.empresa)
        response = self.client.get(self.product_url(self.otra_tienda.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_rejects_foreign_category(self):
        self.client.force_authenticate(self.empresa)
        payload = self.valid_payload(categoria_id=str(self.otra_categoria.id))
        response = self.client.post(self.product_url(), payload, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('categoria_id', response.data)

    def test_rejects_duplicate_skus(self):
        self.client.force_authenticate(self.empresa)
        payload = self.valid_payload(
            variantes=json.dumps([
                {
                    'sku': 'DUP-1',
                    'precio': '10.00',
                    'stock': 1,
                    'stock_minimo': 1,
                    'atributos': {},
                },
                {
                    'sku': 'DUP-1',
                    'precio': '11.00',
                    'stock': 1,
                    'stock_minimo': 1,
                    'atributos': {},
                },
            ])
        )
        response = self.client.post(self.product_url(), payload, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('variantes', response.data)

    @patch('apps.catalogo.services.upload_product_image')
    @patch('apps.catalogo.services.delete_product_image')
    @patch('apps.catalogo.services.Variante.objects.bulk_create')
    def test_cleans_cloudinary_when_database_fails(self, bulk_create, delete_image, upload):
        upload.return_value = {
            'url': 'https://res.cloudinary.com/demo/fallo.png',
            'public_id': 'kantu/test/fallo',
        }
        bulk_create.side_effect = IntegrityError('error de prueba')

        with self.assertRaises(IntegrityError):
            create_product_with_images(
                tienda=self.tienda,
                validated_data={
                    'nombre': 'Producto fallido',
                    'descripcion': 'No debe persistir',
                    'categoria_id': self.categoria.id,
                    'etiquetas': [],
                    'activo': True,
                    'variantes': [{
                        'sku': 'FAIL-1',
                        'nombre': 'Unica',
                        'precio': Decimal('10.00'),
                        'precio_oferta': None,
                        'stock': 0,
                        'stock_minimo': 1,
                        'atributos': {},
                        'activa': True,
                    }],
                    'imagenes': [SimpleUploadedFile(
                        'fallo.png',
                        b'\x89PNG\r\n\x1a\ncontenido',
                        content_type='image/png',
                    )],
                },
            )

        self.assertFalse(Producto.objects.filter(nombre='Producto fallido').exists())
        delete_image.assert_called_once_with('kantu/test/fallo')

    @patch('apps.catalogo.services.upload_product_image')
    def test_all_active_variants_without_stock_are_agotado(self, upload):
        upload.return_value = {
            'url': 'https://res.cloudinary.com/demo/ag agotado.png',
            'public_id': 'kantu/test/agotado',
        }
        self.client.force_authenticate(self.empresa)
        payload = self.valid_payload(
            variantes=json.dumps([{
                'sku': 'AGOT-1',
                'nombre': 'Unica',
                'precio': '40.00',
                'stock': 0,
                'stock_minimo': 2,
                'atributos': {},
                'activa': True,
            }])
        )

        response = self.client.post(self.product_url(), payload, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['stock_total'], 0)
        self.assertTrue(response.data['agotado'])
        self.assertFalse(response.data['en_stock'])

    @patch('apps.catalogo.services.upload_product_image')
    def test_creates_product_with_multiple_variants(self, upload):
        upload.return_value = {
            'url': 'https://res.cloudinary.com/demo/multiple.png',
            'public_id': 'kantu/test/multiple',
        }
        self.client.force_authenticate(self.empresa)
        payload = self.valid_payload(
            variantes=json.dumps([
                {
                    'sku': 'MULTI-S', 'nombre': 'S', 'precio': '50.00',
                    'stock': 3, 'stock_minimo': 1, 'atributos': {'talla': 'S'},
                },
                {
                    'sku': 'MULTI-M', 'nombre': 'M', 'precio': '55.00',
                    'stock': 2, 'stock_minimo': 1, 'atributos': {'talla': 'M'},
                },
            ])
        )

        response = self.client.post(self.product_url(), payload, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data['variantes']), 2)
        self.assertEqual(response.data['stock_total'], 5)

    def test_rejects_negative_values_and_invalid_image(self):
        self.client.force_authenticate(self.empresa)
        negative_payload = self.valid_payload(
            variantes=json.dumps([{
                'sku': 'NEG-1', 'nombre': 'Unica', 'precio': '-1.00',
                'stock': 0, 'stock_minimo': 1, 'atributos': {},
            }])
        )
        negative_response = self.client.post(
            self.product_url(), negative_payload, format='multipart'
        )
        self.assertEqual(negative_response.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_image_payload = self.valid_payload(
            imagenes=SimpleUploadedFile(
                'producto.gif', b'GIF89a', content_type='image/gif'
            )
        )
        invalid_image_response = self.client.post(
            self.product_url(), invalid_image_payload, format='multipart'
        )
        self.assertEqual(invalid_image_response.status_code, status.HTTP_400_BAD_REQUEST)
