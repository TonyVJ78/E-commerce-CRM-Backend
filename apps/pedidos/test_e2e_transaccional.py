import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalogo.models import Categoria, Producto, Variante
from apps.ia.models import EventoUsuario
from apps.pedidos.models import Carrito, ItemCarrito, ItemPedido, Pago, Pedido
from apps.tiendas.models import Tienda
from apps.usuarios.models import Rol, Usuario


@override_settings(STRIPE_SECRET_KEY='sk_test_dummy', STRIPE_USD_BOB_RATE=6.96)
class E2ETransaccionalCompletoTests(APITestCase):
    """
    Plan de Pruebas E2E Transaccional Cruzado:
    CU-13 (Marca y Cloudinary) -> CU-14 (Telemetría e IA con Fallback) ->
    CU-11 (Carrito Multi-Tienda) -> CU-19 (Stripe PaymentIntent, Triggers y Checkout).
    """

    def setUp(self):
        # 1. Configuración de Roles y Usuarios
        self.rol_empresa = Rol.objects.get_or_create(nombre='empresa')[0]
        self.rol_cliente = Rol.objects.get_or_create(nombre='cliente')[0]

        # Tenant Legítimo A
        self.tenant_a = Usuario.objects.create_user(
            email='tenant_a@kantu.bo',
            password='Password123!',
            rol=self.rol_empresa,
        )
        self.tienda_a = Tienda.objects.create(
            propietario=self.tenant_a,
            nombre='Artesanías Andinas',
            slug='artesanias-andinas',
            color_primario='#112233',
            activa=True,
        )

        # Tenant Ajeno B (para prueba de ataque / aislamiento multitenant)
        self.tenant_b = Usuario.objects.create_user(
            email='tenant_b@kantu.bo',
            password='Password123!',
            rol=self.rol_empresa,
        )
        self.tienda_b = Tienda.objects.create(
            propietario=self.tenant_b,
            nombre='Tejidos La Paz',
            slug='tejidos-lapaz',
            activa=True,
        )

        # Cliente Final
        self.cliente = Usuario.objects.create_user(
            email='comprador@kantu.bo',
            password='Password123!',
            rol=self.rol_cliente,
        )

        # Catálogo de Tienda A
        self.categoria = Categoria.objects.create(
            tienda=self.tienda_a,
            nombre='Textiles',
        )
        self.producto = Producto.objects.create(
            tienda=self.tienda_a,
            categoria=self.categoria,
            nombre='Poncho de Alpaca Tradicional',
            slug='poncho-alpaca-tradicional',
            descripcion='Poncho 100% fibra de alpaca fina.',
            activo=True,
        )
        self.variante = Variante.objects.create(
            producto=self.producto,
            nombre='Talla Única - Rojo Andino',
            sku='PON-ALP-ROJ',
            precio=Decimal('100.00'),  # 100.00 BOB
            stock=10,
            activa=True,
        )

    # =========================================================================
    # ESCENARIO COMPLETO TRANSACCIONAL E2E
    # =========================================================================
    @patch('apps.tiendas.services._cloudinary_uploader')
    @patch('stripe.PaymentIntent.create')
    @patch('stripe.PaymentIntent.retrieve')
    def test_e2e_flujo_transaccional_completo(
        self, mock_stripe_retrieve, mock_stripe_create, mock_cloudinary_uploader
    ):
        # ---------------------------------------------------------------------
        # PASO 1 (CU-13): Tenant actualiza identidad de marca en Cloudinary
        # ---------------------------------------------------------------------
        # Mock de Cloudinary Uploader
        mock_uploader_instance = MagicMock()
        mock_uploader_instance.upload.return_value = {
            'secure_url': 'https://res.cloudinary.com/kifsav7n/image/upload/v1234/kantu/tiendas/logo.webp',
            'public_id': 'kantu/tiendas/1/logo/logo_artesanias',
        }
        mock_cloudinary_uploader.return_value = mock_uploader_instance

        # 1.1 Verificación de Aislamiento Multitenant (Intrusión rechazada con HTTP 403)
        self.client.force_authenticate(user=self.tenant_b)
        url_marca = reverse('tienda_identidad', kwargs={'pk': self.tienda_a.pk})
        res_hack = self.client.patch(url_marca, {'color_primario': '#FF0000'}, format='json')
        self.assertEqual(res_hack.status_code, status.HTTP_403_FORBIDDEN)

        # 1.2 Actualización legítima por el dueño de la tienda
        self.client.force_authenticate(user=self.tenant_a)
        valid_png = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00'
            b'\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        fake_logo = SimpleUploadedFile('logo.png', valid_png, content_type='image/png')
        res_marca = self.client.patch(
            url_marca,
            {
                'color_primario': '#0055AA',
                'logo': fake_logo,
            },
            format='multipart',
        )
        self.assertEqual(res_marca.status_code, status.HTTP_200_OK, getattr(res_marca, 'data', None))
        self.tienda_a.refresh_from_db()
        self.assertEqual(self.tienda_a.color_primario, '#0055AA')
        self.assertIn('kifsav7n', self.tienda_a.logo_url)

        # ---------------------------------------------------------------------
        # PASO 2 (CU-14): Cliente entra, telemetría fire-and-forget e IA
        # ---------------------------------------------------------------------
        self.client.force_authenticate(user=self.cliente)

        # 2.1 Envío de telemetría asíncrona sin rol admin (VIEW de producto)
        url_telemetria = reverse('ia_eventos')
        res_telem = self.client.post(
            url_telemetria,
            {
                'tienda_id': self.tienda_a.id,
                'producto_id': self.producto.id,
                'tipo_interaccion': 'VIEW',
            },
            format='json',
        )
        self.assertEqual(res_telem.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            EventoUsuario.objects.filter(
                cliente=self.cliente,
                tienda=self.tienda_a,
                producto=self.producto,
                tipo_evento='VIEW',
            ).exists()
        )

        # 2.2 Consulta de recomendaciones personalizadas de la tienda
        url_recom = f"{reverse('ia_recomendaciones_query')}?tienda_id={self.tienda_a.id}&limit=5"
        res_recom = self.client.get(url_recom)
        self.assertEqual(res_recom.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res_recom.data, list)
        self.assertTrue(len(res_recom.data) > 0)
        self.assertEqual(res_recom.data[0]['id'], self.producto.id)

        # ---------------------------------------------------------------------
        # PASO 3 (CU-11): Adición de producto al carrito multi-tienda
        # ---------------------------------------------------------------------
        url_carrito_add = reverse('agregar_item_carrito')
        res_cart = self.client.post(
            url_carrito_add,
            {
                'tienda_id': self.tienda_a.id,
                'variante_id': self.variante.id,
                'cantidad': 1,
            },
            format='json',
        )
        self.assertEqual(res_cart.status_code, status.HTTP_201_CREATED)
        
        # Validar existencia del carrito y del item para el cliente
        carrito = Carrito.objects.get(cliente=self.cliente, tienda=self.tienda_a)
        item = ItemCarrito.objects.get(carrito=carrito, variante=self.variante)
        self.assertEqual(item.cantidad, 1)

        # ---------------------------------------------------------------------
        # PASO 4 (CU-19): Pasarela Stripe y Checkout con Triggers de PostgreSQL
        # ---------------------------------------------------------------------
        # 4.1 Iniciar intento de pago Stripe (cálculo BOB a USD centavos)
        # Total carrito = 100.00 BOB -> a tasa 6.96 = 14.3678 USD -> 1437 centavos
        mock_stripe_create.return_value = MagicMock(
            id='pi_test_kantu_9999',
            client_secret='pi_test_kantu_9999_secret_xyz',
            amount=1437,
            currency='usd',
        )

        url_pago_intento = reverse('carrito_pago_intento')
        res_intento = self.client.post(url_pago_intento, format='json')
        self.assertEqual(res_intento.status_code, status.HTTP_200_OK)
        self.assertEqual(res_intento.data['client_secret'], 'pi_test_kantu_9999_secret_xyz')
        self.assertEqual(res_intento.data['payment_intent_id'], 'pi_test_kantu_9999')
        self.assertIn('monto_usd', res_intento.data)

        # 4.2 Checkout transaccional atómico
        mock_stripe_retrieve.return_value = MagicMock(
            id='pi_test_kantu_9999',
            status='succeeded',
            metadata={'cliente_id': str(self.cliente.id)},
            amount=1437,
        )

        stock_inicial = self.variante.stock  # 10
        url_checkout = reverse('carrito_checkout')
        res_checkout = self.client.post(
            url_checkout,
            {
                'metodo_pago': 'Stripe',
                'payment_intent_id': 'pi_test_kantu_9999',
            },
            format='json',
        )
        self.assertEqual(res_checkout.status_code, status.HTTP_201_CREATED)
        self.assertIn('pedidos', res_checkout.data)
        pedido_id = res_checkout.data['pedidos'][0]

        # Validaciones de Integridad y Triggers de PostgreSQL:
        pedido = Pedido.objects.get(pk=pedido_id)
        
        # Validar que trg_recalcular_total_pedido fijó los montos
        self.assertEqual(pedido.subtotal, Decimal('100.00'))
        self.assertEqual(pedido.total, Decimal('100.00'))

        # Validar que el Pago se creó con el monto idéntico recargado de BD (pedido.refresh_from_db())
        pago = Pago.objects.get(pedido=pedido)
        self.assertEqual(pago.monto, Decimal('100.00'))
        self.assertEqual(pago.estado, 'pagado')
        self.assertEqual(pago.referencia_transaccion, 'pi_test_kantu_9999')

        # Validar que trg_actualizar_stock_item_pedido descontó el stock automáticamente
        self.variante.refresh_from_db()
        self.assertEqual(self.variante.stock, stock_inicial - 1)  # 10 - 1 = 9

        # Validar que el carrito del cliente fue vaciado tras la compra
        self.assertEqual(carrito.items.count(), 0)

    # =========================================================================
    # ESCENARIOS DE RESILIENCIA Y FALLBACK
    # =========================================================================
    def test_ia_fallback_silencioso_sin_romper_ux(self):
        """
        CU-14: Si el motor de IA falla o cae, el backend DEBE retornar [] con HTTP 200.
        Nunca debe propagar un HTTP 500 al cliente.
        """
        self.client.force_authenticate(user=self.cliente)
        url_recom = f"{reverse('ia_recomendaciones_query')}?tienda_id={self.tienda_a.id}"

        with patch('apps.ia.views.obtener_recomendaciones_cliente', side_effect=RuntimeError('Database Connection Dropped')):
            response = self.client.get(url_recom)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data, [])

    @patch('stripe.Refund.create')
    @patch('stripe.PaymentIntent.retrieve')
    def test_checkout_rollback_atomico_si_stock_insuficiente(self, mock_stripe_retrieve, mock_refund):
        """
        CU-19: Si al momento de comprar el stock es insuficiente,
        el trigger de PostgreSQL trg_actualizar_stock_item_pedido rechaza la operación
        y revierte atómicamente la transacción sin crear pedidos ni pagos huérfanos.
        """
        self.client.force_authenticate(user=self.cliente)

        # Dejar la variante con 0 de stock
        self.variante.stock = 0
        self.variante.save()

        # Forzar un item en el carrito
        carrito = Carrito.objects.create(cliente=self.cliente, tienda=self.tienda_a)
        ItemCarrito.objects.create(carrito=carrito, tienda=self.tienda_a, variante=self.variante, cantidad=1)

        mock_stripe_retrieve.return_value = MagicMock(
            id='pi_test_sin_stock',
            status='succeeded',
            metadata={'cliente_id': str(self.cliente.id)},
            amount=1437,
        )

        url_checkout = reverse('carrito_checkout')
        response = self.client.post(
            url_checkout,
            {
                'metodo_pago': 'Stripe',
                'payment_intent_id': 'pi_test_sin_stock',
            },
            format='json',
        )

        # Debe responder Bad Request
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        
        # Validar que NO se creó ningún pedido huérfano
        self.assertEqual(Pedido.objects.filter(cliente=self.cliente).count(), 0)
        self.assertEqual(Pago.objects.count(), 0)
