from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalogo.models import Categoria, Producto, Variante
from apps.pedidos.models import ItemPedido, Pedido
from apps.tiendas.models import Tienda
from apps.usuarios.models import Rol, Usuario

from .models import EventoUsuario


class RecomendacionesCU14APITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cliente_role, _ = Rol.objects.get_or_create(nombre='cliente')
        empresa_role, _ = Rol.objects.get_or_create(nombre='empresa')
        cls.cliente = Usuario.objects.create_user(
            email='cliente-cu14@example.com',
            password='Password123!',
            rol=cliente_role,
        )
        cls.otro_cliente = Usuario.objects.create_user(
            email='otro-cliente-cu14@example.com',
            password='Password123!',
            rol=cliente_role,
        )
        cls.empresa = Usuario.objects.create_user(
            email='empresa-cu14@example.com',
            password='Password123!',
            rol=empresa_role,
        )
        cls.otra_empresa = Usuario.objects.create_user(
            email='otra-empresa-cu14@example.com',
            password='Password123!',
            rol=empresa_role,
        )
        cls.tienda = Tienda.objects.create(
            propietario=cls.empresa,
            nombre='Tienda CU14',
            slug='tienda-cu14',
        )
        cls.otra_tienda = Tienda.objects.create(
            propietario=cls.otra_empresa,
            nombre='Otra Tienda CU14',
            slug='otra-tienda-cu14',
        )
        cls.calzado = Categoria.objects.create(
            tienda=cls.tienda,
            nombre='Calzado',
        )
        cls.hogar = Categoria.objects.create(
            tienda=cls.tienda,
            nombre='Hogar',
        )
        cls.producto_calzado = cls._create_product(
            cls.tienda,
            cls.calzado,
            'Zapatilla deportiva',
            'zapatilla-deportiva',
            'ZAP-CU14',
        )
        cls.producto_hogar = cls._create_product(
            cls.tienda,
            cls.hogar,
            'Jarrón artesanal',
            'jarron-artesanal',
            'JAR-CU14',
        )
        cls.producto_otra_tienda = cls._create_product(
            cls.otra_tienda,
            None,
            'Producto de otro tenant',
            'otro-tenant',
            'OTRO-CU14',
        )

    @classmethod
    def _create_product(
        cls,
        tienda,
        categoria,
        nombre,
        slug,
        sku,
        *,
        activo=True,
        variante_activa=True,
        stock=10,
    ):
        product = Producto.objects.create(
            tienda=tienda,
            categoria=categoria,
            nombre=nombre,
            slug=slug,
            descripcion=f'Descripción de {nombre}',
            etiquetas=['deportivo'] if categoria and categoria.nombre == 'Calzado' else [],
            activo=activo,
        )
        Variante.objects.create(
            producto=product,
            nombre='Única',
            sku=sku,
            precio=Decimal('100.00'),
            stock=stock,
            stock_minimo=1,
            activa=variante_activa,
        )
        return product

    def setUp(self):
        self.recommendations_url = reverse(
            'recomendaciones_tienda',
            kwargs={'tienda_id': self.tienda.id},
        )
        self.interactions_url = reverse('recomendaciones_interaccion')

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.cliente)

    def post_interaction(self, event_type, product=None, term=''):
        payload = {
            'tienda_id': self.tienda.id,
            'tipo_interaccion': event_type,
        }
        if product is not None:
            payload['producto_id'] = product.id
        if term:
            payload['termino_busqueda'] = term
        return self.client.post(self.interactions_url, payload, format='json')

    def test_01_authenticated_client_gets_recommendations(self):
        self.authenticate()
        response = self.client.get(self.recommendations_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data), 0)

    def test_02_anonymous_user_gets_401(self):
        response = self.client.get(self.recommendations_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_03_non_client_role_gets_403(self):
        self.authenticate(self.empresa)
        response = self.client.get(self.recommendations_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_04_recommendations_only_include_requested_store(self):
        self.authenticate()
        response = self.client.get(self.recommendations_url)
        self.assertTrue(all(item['tienda_id'] == self.tienda.id for item in response.data))

    def test_05_never_mixes_tenants_even_with_foreign_history(self):
        EventoUsuario.objects.create(
            cliente=self.cliente,
            tienda=self.otra_tienda,
            producto=self.producto_otra_tienda,
            tipo_evento=EventoUsuario.TipoEvento.CLICK,
        )
        self.authenticate()
        response = self.client.get(self.recommendations_url)
        ids = {item['id'] for item in response.data}
        self.assertNotIn(self.producto_otra_tienda.id, ids)

    def test_06_inactive_product_is_not_recommended(self):
        inactive = self._create_product(
            self.tienda,
            self.calzado,
            'Producto inactivo',
            'producto-inactivo-cu14',
            'INACTIVO-CU14',
            activo=False,
        )
        self.authenticate()
        response = self.client.get(self.recommendations_url)
        self.assertNotIn(inactive.id, {item['id'] for item in response.data})

    def test_07_product_without_active_available_variant_is_excluded(self):
        inactive_variant = self._create_product(
            self.tienda,
            self.calzado,
            'Variante inactiva',
            'variante-inactiva-cu14',
            'VAR-INACTIVA-CU14',
            variante_activa=False,
        )
        no_stock = self._create_product(
            self.tienda,
            self.calzado,
            'Sin stock',
            'sin-stock-cu14',
            'SIN-STOCK-CU14',
            stock=0,
        )
        self.authenticate()
        response = self.client.get(self.recommendations_url)
        ids = {item['id'] for item in response.data}
        self.assertNotIn(inactive_variant.id, ids)
        self.assertNotIn(no_stock.id, ids)

    def test_08_client_does_not_use_another_clients_interactions(self):
        for _ in range(3):
            EventoUsuario.objects.create(
                cliente=self.otro_cliente,
                tienda=self.tienda,
                producto=self.producto_hogar,
                tipo_evento=EventoUsuario.TipoEvento.CLICK,
            )
        EventoUsuario.objects.create(
            cliente=self.cliente,
            tienda=self.tienda,
            producto=self.producto_calzado,
            tipo_evento=EventoUsuario.TipoEvento.CLICK,
        )
        self.authenticate()
        response = self.client.get(self.recommendations_url)
        self.assertEqual(response.data[0]['id'], self.producto_calzado.id)

    def test_09_view_is_persisted(self):
        self.authenticate()
        response = self.post_interaction('VIEW', self.producto_calzado)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(EventoUsuario.objects.filter(
            cliente=self.cliente,
            producto=self.producto_calzado,
            tipo_evento='VIEW',
        ).exists())

    def test_10_click_is_persisted(self):
        self.authenticate()
        response = self.post_interaction('CLICK', self.producto_calzado)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['tipo_interaccion'], 'CLICK')

    def test_11_search_is_persisted(self):
        self.authenticate()
        response = self.post_interaction('SEARCH', term='deportivo')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(EventoUsuario.objects.filter(
            cliente=self.cliente,
            tienda=self.tienda,
            termino_busqueda='deportivo',
        ).exists())

    def test_12_foreign_store_product_interaction_is_rejected(self):
        self.authenticate()
        response = self.client.post(self.interactions_url, {
            'tienda_id': self.tienda.id,
            'producto_id': self.producto_otra_tienda.id,
            'tipo_interaccion': 'CLICK',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(EventoUsuario.objects.filter(
            cliente=self.cliente,
            producto=self.producto_otra_tienda,
            tienda=self.tienda,
        ).exists())

    def test_13_previous_purchase_influences_ranking(self):
        pedido = Pedido.objects.create(
            cliente=self.cliente,
            tienda=self.tienda,
            estado_actual='completado',
            subtotal=Decimal('100.00'),
            total=Decimal('100.00'),
        )
        ItemPedido.objects.create(
            tienda=self.tienda,
            pedido=pedido,
            variante=self.producto_hogar.variantes.first(),
            cantidad=2,
            precio_unitario=Decimal('100.00'),
        )
        self.authenticate()
        response = self.client.get(self.recommendations_url)
        self.assertEqual(response.data[0]['id'], self.producto_hogar.id)

    def test_14_cart_addition_persists_signal_and_influences_ranking(self):
        self.authenticate()
        response = self.client.post(reverse('agregar_item_carrito'), {
            'tienda_id': self.tienda.id,
            'variante_id': self.producto_hogar.variantes.first().id,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(EventoUsuario.objects.filter(
            cliente=self.cliente,
            producto=self.producto_hogar,
            tipo_evento='CART',
        ).exists())
        recommendations = self.client.get(self.recommendations_url)
        self.assertEqual(recommendations.data[0]['id'], self.producto_hogar.id)

    def test_15_fallback_works_without_history(self):
        self.authenticate()
        response = self.client.get(self.recommendations_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_16_fallback_does_not_mix_stores(self):
        self.authenticate()
        response = self.client.get(self.recommendations_url)
        self.assertTrue(all(item['tienda_id'] == self.tienda.id for item in response.data))

    def test_17_limit_is_applied(self):
        self.authenticate()
        response = self.client.get(self.recommendations_url, {'limit': 1})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_18_limit_above_maximum_is_rejected(self):
        self.authenticate()
        response = self.client.get(self.recommendations_url, {'limit': 21})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_19_response_has_no_duplicate_products(self):
        self.authenticate()
        response = self.client.get(self.recommendations_url)
        ids = [item['id'] for item in response.data]
        self.assertEqual(len(ids), len(set(ids)))

    def test_20_invalid_payload_returns_controlled_400(self):
        self.authenticate()
        response = self.client.post(self.interactions_url, {
            'tienda_id': self.tienda.id,
            'tipo_interaccion': 'SEARCH',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('termino_busqueda', response.data)

    def test_21_persisted_interaction_changes_real_ranking(self):
        self.authenticate()
        post_response = self.post_interaction('CLICK', self.producto_calzado)
        self.assertEqual(post_response.status_code, status.HTTP_201_CREATED)
        get_response = self.client.get(self.recommendations_url)
        self.assertEqual(get_response.data[0]['id'], self.producto_calzado.id)

    def test_22_immediate_duplicate_event_is_deduplicated(self):
        self.authenticate()
        self.post_interaction('VIEW', self.producto_calzado)
        self.post_interaction('VIEW', self.producto_calzado)
        self.assertEqual(EventoUsuario.objects.filter(
            cliente=self.cliente,
            tienda=self.tienda,
            producto=self.producto_calzado,
            tipo_evento='VIEW',
        ).count(), 1)
