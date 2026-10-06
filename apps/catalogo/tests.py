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
from .services import adjust_variant_stock, create_product_with_images


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

    def _stock_variant(self, stock=10, tienda=None):
        producto = Producto.objects.create(
            tienda=tienda or self.tienda,
            nombre=f'Producto stock {Variante.objects.count()}',
            slug=f'producto-stock-{Variante.objects.count()}',
        )
        return Variante.objects.create(
            producto=producto,
            nombre='Talla única',
            sku=f'STOCK-{Variante.objects.count()}',
            precio=Decimal('12.00'),
            stock=stock,
        )

    def _stock_url(self, variante, tienda=None):
        return reverse(
            'variante-stock-ajustes',
            kwargs={'tienda_id': (tienda or self.tienda).id, 'variante_id': variante.id},
        )

    def test_ajuste_stock_suma_y_resta_deja_historial_completo(self):
        variante = self._stock_variant(stock=10)
        self._auth()

        response = self.client.post(
            self._stock_url(variante), {'delta': 5, 'reason': '  Recepción  ', 'tipo_ajuste': 'INGRESO'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['previous_stock'], 10)
        self.assertEqual(response.data['delta'], 5)
        self.assertEqual(response.data['resulting_stock'], 15)
        self.assertEqual(response.data['reason'], '[INGRESO] Recepción')
        self.assertEqual(response.data['actor'], self.empresa.id)
        self.assertIn('created_at', response.data)

        # Verificar registro en LogAuditoria central
        from apps.usuarios.models import LogAuditoria
        log = LogAuditoria.objects.filter(tabla='variante', registro_id=variante.id).latest('id')
        self.assertEqual(log.accion, 'ACTUALIZAR')
        self.assertEqual(log.datos_previos['stock'], 10)
        self.assertEqual(log.datos_nuevos['stock'], 15)

        response = self.client.post(
            self._stock_url(variante), {'delta': -3, 'reason': 'Venta corregida'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['previous_stock'], 15)
        self.assertEqual(response.data['resulting_stock'], 12)
        self.assertEqual(variante.stock_movimientos.count(), 2)

    def test_ajuste_stock_soporta_nuevo_stock_absoluto(self):
        variante = self._stock_variant(stock=10)
        self._auth()

        # Ajuste a valor absoluto mayor
        response = self.client.post(
            self._stock_url(variante), {'nuevo_stock': 25, 'reason': 'Conteo de inventario', 'tipo_ajuste': 'CORRECCION'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['previous_stock'], 10)
        self.assertEqual(response.data['delta'], 15)
        self.assertEqual(response.data['resulting_stock'], 25)

        # Ajuste a valor absoluto idéntico debe fallar
        response_same = self.client.post(
            self._stock_url(variante), {'nuevo_stock': 25, 'reason': 'Conteo repetido'}, format='json'
        )
        self.assertEqual(response_same.status_code, status.HTTP_400_BAD_REQUEST)

        # No permitir ambos
        response_both = self.client.post(
            self._stock_url(variante), {'delta': 2, 'nuevo_stock': 25, 'reason': 'Ambos'}, format='json'
        )
        self.assertEqual(response_both.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['previous_stock'], 15)
        self.assertEqual(response.data['resulting_stock'], 12)
        self.assertEqual(variante.stock_movimientos.count(), 2)

    def test_ajuste_stock_rechaza_delta_y_razon_invalidos(self):
        variante = self._stock_variant()
        self._auth()
        url = self._stock_url(variante)
        for payload in (
            [],
            'scalar',
            7,
            None,
            {'delta': 0, 'reason': 'Motivo'},
            {'delta': '1', 'reason': 'Motivo'},
            {'delta': '1.5', 'reason': 'Motivo'},
            {'delta': 1.0, 'reason': 'Motivo'},
            {'delta': 1.5, 'reason': 'Motivo'},
            {'delta': True, 'reason': 'Motivo'},
            {'delta': None, 'reason': 'Motivo'},
            {'delta': 1, 'reason': '   '},
            {'delta': 1, 'reason': 'x' * 256},
            {'reason': 'Motivo'},
        ):
            with self.subTest(payload=payload):
                response = self.client.post(url, payload, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        variante.refresh_from_db()
        self.assertEqual(variante.stock, 10)
        self.assertEqual(variante.stock_movimientos.count(), 0)

    def test_ajuste_stock_impide_stock_negativo(self):
        variante = self._stock_variant(stock=2)
        self._auth()
        response = self.client.post(
            self._stock_url(variante), {'delta': -3, 'reason': 'Corrección'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        variante.refresh_from_db()
        self.assertEqual(variante.stock, 2)
        self.assertEqual(variante.stock_movimientos.count(), 0)

    def test_ajuste_stock_exige_empresa_propietaria(self):
        variante = self._stock_variant()
        url = self._stock_url(variante)
        self._auth(self.cliente)
        self.assertEqual(
            self.client.post(url, {'delta': 1, 'reason': 'Ajuste'}, format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self._auth(self.otra_empresa)
        self.assertEqual(
            self.client.post(url, {'delta': 1, 'reason': 'Ajuste'}, format='json').status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self._auth(self.empresa)
        foreign_variant = self._stock_variant(tienda=self.otra_tienda)
        self.assertEqual(
            self.client.post(
                self._stock_url(foreign_variant),
                {'delta': 1, 'reason': 'Ajuste'}, format='json',
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_falla_al_crear_movimiento_revierte_el_stock(self):
        variante = self._stock_variant(stock=10)
        with patch('apps.catalogo.services.VarianteStockMovimiento.objects.create', side_effect=IntegrityError):
            with self.assertRaises(IntegrityError):
                adjust_variant_stock(variante_id=variante.id, actor=self.empresa, delta=2, reason='Recepción')
        variante.refresh_from_db()
        self.assertEqual(variante.stock, 10)
        self.assertEqual(variante.stock_movimientos.count(), 0)

    def test_historial_es_solo_lectura_y_esta_limitado_a_tienda(self):
        propia = self._stock_variant(stock=10)
        ajena = self._stock_variant(tienda=self.otra_tienda)
        self._auth()
        own_url = self._stock_url(propia)
        first_response = self.client.post(
            own_url, {'delta': 1, 'reason': 'Recepción'}, format='json'
        )
        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        second_response = self.client.post(
            own_url, {'delta': 2, 'reason': 'Ajuste adicional'}, format='json'
        )
        self.assertEqual(second_response.status_code, status.HTTP_201_CREATED)
        for response, previous, delta, resulting, reason in (
            (first_response, 10, 1, 11, 'Recepción'),
            (second_response, 11, 2, 13, 'Ajuste adicional'),
        ):
            self.assertIn('id', response.data)
            self.assertEqual(response.data['variante'], propia.id)
            self.assertEqual(response.data['previous_stock'], previous)
            self.assertEqual(response.data['delta'], delta)
            self.assertEqual(response.data['resulting_stock'], resulting)
            self.assertEqual(response.data['actor'], self.empresa.id)
            self.assertEqual(response.data['reason'], reason)
            self.assertIn('created_at', response.data)

        response = self.client.get(own_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]['id'], second_response.data['id'])
        self.assertEqual(response.data[0]['previous_stock'], 11)
        self.assertEqual(response.data[0]['delta'], 2)
        self.assertEqual(response.data[0]['resulting_stock'], 13)
        self.assertEqual(response.data[0]['actor'], self.empresa.id)
        self.assertEqual(response.data[0]['reason'], 'Ajuste adicional')
        self.assertIn('created_at', response.data[0])
        self.assertEqual(response.data[1]['id'], first_response.data['id'])
        self.assertEqual(response.data[1]['previous_stock'], 10)
        self.assertEqual(response.data[1]['delta'], 1)
        self.assertEqual(response.data[1]['resulting_stock'], 11)
        self.assertEqual(response.data[1]['actor'], self.empresa.id)
        self.assertEqual(response.data[1]['reason'], 'Recepción')
        self.assertIn('created_at', response.data[1])
        self.assertEqual(self.client.get(self._stock_url(ajena)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.delete(own_url).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_patch_producto_rechaza_stock_pero_permite_precio(self):
        variante = self._stock_variant()
        self._auth()
        product_url = reverse(
            'producto-detail', kwargs={'tienda_id': self.tienda.id, 'producto_id': variante.producto_id}
        )
        response = self.client.patch(product_url, {'stock': 99}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        variante.refresh_from_db()
        self.assertEqual(variante.stock, 10)
        response = self.client.patch(product_url, {'precio': '15.00'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        variante.refresh_from_db()
        self.assertEqual(variante.precio, Decimal('15.00'))


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
