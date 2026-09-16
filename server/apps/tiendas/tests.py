from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalogo.services import (
    CloudinaryConfigurationError,
    CloudinaryUploadError,
    MAX_IMAGE_SIZE,
)
from apps.usuarios.models import LogAuditoria, Rol, Usuario

from .models import Tienda
from .services import upload_store_logo


class TiendaIdentidadAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        rol_empresa, _ = Rol.objects.get_or_create(nombre='empresa')
        rol_cliente, _ = Rol.objects.get_or_create(nombre='cliente')
        rol_admin, _ = Rol.objects.get_or_create(nombre='administrador')
        cls.empresa_a = Usuario.objects.create_user(
            email='empresa-a-identidad@example.com',
            password='Password123!',
            rol=rol_empresa,
        )
        cls.empresa_b = Usuario.objects.create_user(
            email='empresa-b-identidad@example.com',
            password='Password123!',
            rol=rol_empresa,
        )
        cls.cliente = Usuario.objects.create_user(
            email='cliente-identidad@example.com',
            password='Password123!',
            rol=rol_cliente,
        )
        cls.admin = Usuario.objects.create_user(
            email='admin-identidad@example.com',
            password='Password123!',
            rol=rol_admin,
        )
        cls.tienda_a = Tienda.objects.create(
            propietario=cls.empresa_a,
            nombre='Tienda A',
            slug='tienda-a',
            color_primario='#C8102E',
        )
        cls.tienda_b = Tienda.objects.create(
            propietario=cls.empresa_b,
            nombre='Tienda B',
            slug='tienda-b',
            color_primario='#27AE60',
        )

    def setUp(self):
        self.url_a = reverse('tienda_identidad', kwargs={'pk': self.tienda_a.pk})

    def auth(self, user=None):
        self.client.force_authenticate(user=user or self.empresa_a)

    @staticmethod
    def image(name='logo.jpg', content_type='image/jpeg', content=b'\xff\xd8\xfflogo'):
        return SimpleUploadedFile(name, content, content_type=content_type)

    def test_usuario_no_autenticado_recibe_401(self):
        response = self.client.get(self.url_a)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cliente_y_administrador_reciben_403(self):
        for user in (self.cliente, self.admin):
            with self.subTest(rol=user.rol.nombre):
                self.auth(user)
                response = self.client.get(self.url_a)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_empresa_consulta_solo_su_tienda(self):
        self.auth()
        response = self.client.get(self.url_a)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['slug'], 'tienda-a')
        self.assertNotIn('propietario', response.data)

        foreign_url = reverse('tienda_identidad', kwargs={'pk': self.tienda_b.pk})
        self.assertEqual(self.client.get(foreign_url).status_code, status.HTTP_404_NOT_FOUND)
        missing_url = reverse('tienda_identidad', kwargs={'pk': 999999})
        self.assertEqual(self.client.get(missing_url).status_code, status.HTTP_404_NOT_FOUND)

    def test_empresa_b_puede_editar_su_tienda(self):
        self.auth(self.empresa_b)
        url = reverse('tienda_identidad', kwargs={'pk': self.tienda_b.pk})
        response = self.client.patch(url, {'color_primario': '#123ABC'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_actualizacion_persiste_y_se_audita(self):
        self.auth()
        response = self.client.patch(
            self.url_a,
            {'slug': 'Nueva Tienda Á', 'color_primario': '#a1b2c3'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['slug'], 'nueva-tienda-a')
        self.assertEqual(response.data['color_primario'], '#A1B2C3')

        self.tienda_a.refresh_from_db()
        self.assertEqual(self.tienda_a.slug, 'nueva-tienda-a')
        self.assertEqual(self.tienda_a.color_primario, '#A1B2C3')
        self.assertTrue(
            LogAuditoria.objects.filter(
                usuario=self.empresa_a,
                tabla_afectada='tienda',
                registro_id=self.tienda_a.pk,
                accion='ACTUALIZAR',
            ).exists()
        )
        refreshed = self.client.get(self.url_a)
        self.assertEqual(refreshed.data['slug'], 'nueva-tienda-a')

    def test_conservar_mismo_slug_no_da_falso_duplicado(self):
        self.auth()
        response = self.client.patch(self.url_a, {'slug': 'tienda-a'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_slug_duplicado_invalido_y_color_invalido_no_guardan(self):
        self.auth()
        casos = (
            ({'slug': 'tienda-b', 'color_primario': '#111111'}, 'slug'),
            ({'slug': '---', 'color_primario': '#111111'}, 'slug'),
            ({'slug': 'slug-valido', 'color_primario': 'rojo'}, 'color_primario'),
            ({'slug': '', 'color_primario': '#111111'}, 'slug'),
        )
        for payload, field in casos:
            with self.subTest(payload=payload):
                response = self.client.patch(self.url_a, payload, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.data)
                self.tienda_a.refresh_from_db()
                self.assertEqual(self.tienda_a.slug, 'tienda-a')
                self.assertEqual(self.tienda_a.color_primario, '#C8102E')

    def test_payload_no_puede_cambiar_propietario(self):
        self.auth()
        response = self.client.patch(
            self.url_a,
            {'propietario': self.empresa_b.pk, 'color_primario': '#ABCDEF'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.tienda_a.refresh_from_db()
        self.assertEqual(self.tienda_a.propietario_id, self.empresa_a.pk)

    @patch('apps.tiendas.serializers.upload_store_logo')
    def test_logo_valido_se_sube_y_persiste(self, mock_upload):
        mock_upload.return_value = {
            'url': 'https://res.cloudinary.com/demo/image/upload/logo.jpg',
            'public_id': 'kantu/tiendas/1/logo/abc',
        }
        self.auth()
        response = self.client.patch(
            self.url_a,
            {'logo': self.image()},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['logo_url'], mock_upload.return_value['url'])
        self.tienda_a.refresh_from_db()
        self.assertEqual(self.tienda_a.logo_url, mock_upload.return_value['url'])

    @patch('apps.tiendas.serializers.upload_store_logo')
    def test_logo_invalido_no_llama_al_proveedor(self, mock_upload):
        self.auth()
        casos = (
            self.image('logo.gif', 'image/gif', b'GIF89a-falso'),
            self.image('logo.txt', 'image/jpeg'),
            self.image('logo.png', 'image/png', b'contenido-falso'),
            self.image('logo.jpg', 'image/jpeg', b'\xff\xd8\xff' + b'x' * MAX_IMAGE_SIZE),
        )
        for logo in casos:
            with self.subTest(name=logo.name):
                response = self.client.patch(self.url_a, {'logo': logo}, format='multipart')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('logo', response.data)
        mock_upload.assert_not_called()

    @patch('apps.tiendas.serializers.upload_store_logo')
    def test_fallo_de_proveedor_no_guarda_otros_cambios(self, mock_upload):
        mock_upload.side_effect = CloudinaryUploadError('Proveedor temporalmente no disponible.')
        self.auth()
        response = self.client.patch(
            self.url_a,
            {'logo': self.image(), 'color_primario': '#000000'},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn('logo', response.data)
        self.tienda_a.refresh_from_db()
        self.assertEqual(self.tienda_a.color_primario, '#C8102E')

    @patch('apps.tiendas.serializers.upload_store_logo')
    def test_proveedor_no_configurado_es_error_controlado(self, mock_upload):
        mock_upload.side_effect = CloudinaryConfigurationError('Cloudinary no está configurado.')
        self.auth()
        response = self.client.patch(
            self.url_a,
            {'logo': self.image()},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn('Cloudinary', response.data['logo'][0])

    @patch('apps.tiendas.serializers.upload_store_logo')
    def test_cambiar_slug_color_sin_logo_no_requiere_cloudinary(self, mock_upload):
        self.auth()
        response = self.client.patch(
            self.url_a,
            {'slug': 'sin-logo', 'color_primario': '#112233'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_upload.assert_not_called()

    def test_disponibilidad_slug_respeta_tenant_y_excluye_instancia(self):
        self.auth()
        url = reverse('tienda_slug_disponible', kwargs={'pk': self.tienda_a.pk})
        actual = self.client.get(url, {'slug': 'tienda-a'})
        ocupado = self.client.get(url, {'slug': 'tienda-b'})
        libre = self.client.get(url, {'slug': 'Slug Nuevo'})
        self.assertTrue(actual.data['disponible'])
        self.assertFalse(ocupado.data['disponible'])
        self.assertTrue(libre.data['disponible'])
        self.assertEqual(libre.data['slug'], 'slug-nuevo')

        foreign_url = reverse('tienda_slug_disponible', kwargs={'pk': self.tienda_b.pk})
        self.assertEqual(
            self.client.get(foreign_url, {'slug': 'otro'}).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    @patch(
        'apps.tiendas.views.TiendaIdentidadView.get_object',
        side_effect=RuntimeError('detalle-interno-sensible'),
    )
    def test_error_inesperado_no_expone_detalles_internos(self, _mock_get_object):
        self.auth()
        response = self.client.get(self.url_a)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertNotIn('detalle-interno-sensible', str(response.data))
        self.assertEqual(
            response.data['detail'],
            'No se pudo procesar la identidad de marca.',
        )


class TiendaLogoServiceTests(APITestCase):
    @patch('apps.tiendas.services._cloudinary_uploader')
    def test_logo_se_separa_en_carpeta_del_tenant(self, mock_uploader_factory):
        uploader = Mock()
        uploader.upload.return_value = {
            'secure_url': 'https://res.cloudinary.com/demo/logo.png',
            'public_id': 'kantu/tiendas/42/logo/abc',
        }
        mock_uploader_factory.return_value = uploader

        result = upload_store_logo(self.image(), 42)

        self.assertEqual(result['url'], uploader.upload.return_value['secure_url'])
        self.assertEqual(uploader.upload.call_args.kwargs['folder'], 'kantu/tiendas/42/logo')

    @staticmethod
    def image():
        return SimpleUploadedFile('logo.png', b'\x89PNG\r\n\x1a\nlogo', content_type='image/png')
