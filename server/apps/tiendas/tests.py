from datetime import datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.catalogo.models import Producto, Variante
from apps.pedidos.models import Carrito, ItemCarrito, ItemPedido, Pedido
from apps.pedidos.views import _usd_centavos
from apps.usuarios.models import Rol, Usuario
from .models import Tienda
from .services import consultar_panel_tienda


class PanelTiendaTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        empresa = Rol.objects.get_or_create(nombre='empresa')[0]
        cliente = Rol.objects.get_or_create(nombre='cliente')[0]
        cls.empresa = Usuario.objects.create_user(email='panel@tests.local', rol=empresa)
        cls.otra_empresa = Usuario.objects.create_user(email='otra@tests.local', rol=empresa)
        cls.cliente = Usuario.objects.create_user(email='cliente@tests.local', rol=cliente)
        cls.tienda = Tienda.objects.create(propietario=cls.empresa, nombre='Kantu prueba')
        cls.segunda = Tienda.objects.create(propietario=cls.empresa, nombre='Segunda')
        cls.ajena = Tienda.objects.create(propietario=cls.otra_empresa, nombre='Ajena')
        cls.producto = Producto.objects.create(tienda=cls.tienda, nombre='Producto')
        cls.variante = Variante.objects.create(
            producto=cls.producto, nombre='Azul', sku='AZUL', precio='10.00',
            stock=3, stock_minimo=5,
        )

    def setUp(self):
        self.client.force_authenticate(self.empresa)

    def url(self, endpoint='dashboard_tienda', tienda=None):
        return reverse(endpoint, kwargs={'tienda_id': (tienda or self.tienda).pk})

    def alertas(self, tienda=None):
        response = self.client.get(self.url('alertas_stock', tienda))
        self.assertEqual(response.status_code, 200)
        return response.data

    def panel(self, tienda=None):
        response = self.client.get(self.url(tienda=tienda))
        self.assertEqual(response.status_code, 200)
        return response.data

    def stock(self, stock, **extra):
        Variante.objects.filter(pk=self.variante.pk).update(stock=stock, **extra)

    def pedido(self, tienda=None, cantidad=0, dias=0, estado='pendiente', total='10.25'):
        tienda = tienda or self.tienda
        pedido = Pedido.objects.create(
            tienda=tienda, cliente=self.cliente, subtotal=total, total=total,
            estado_actual=estado,
        )
        fecha = timezone.make_aware(datetime.combine(timezone.localdate() - timedelta(days=dias), time(12)))
        Pedido.objects.filter(pk=pedido.pk).update(fecha=fecha)
        if cantidad:
            # Usar los triggers reales para descuento y recálculo del total.
            producto = Producto.objects.create(tienda=tienda, nombre='Venta')
            variante = Variante.objects.create(
                producto=producto, sku=f'VENTA-{pedido.pk}', precio='10.25', stock=100,
            )
            ItemPedido.objects.create(
                tienda=tienda, pedido=pedido, variante=variante,
                cantidad=cantidad, precio_unitario=Decimal('10.25'),
            )
        return pedido

    def test_stock_3_minimo_5_aparece_con_identificadores(self):
        data = self.alertas()
        self.assertEqual(data['cantidad'], 1)
        self.assertEqual(data['alertas_stock'][0], {
            'producto_id': self.producto.pk, 'producto_nombre': 'Producto',
            'variante_id': self.variante.pk, 'variante_nombre': 'Azul', 'sku': 'AZUL',
            'stock': 3, 'stock_minimo': 5,
        })

    def test_stock_igual_minimo_no_aparece(self):
        self.stock(5)
        self.assertEqual(self.alertas()['cantidad'], 0)

    def test_stock_mayor_minimo_no_aparece(self):
        self.stock(6)
        self.assertEqual(self.alertas()['cantidad'], 0)

    def test_variante_inactiva_no_aparece(self):
        self.stock(3, activa=False)
        self.assertEqual(self.alertas()['cantidad'], 0)

    def test_minimo_cero_no_aparece(self):
        self.stock(0, stock_minimo=0)
        self.assertEqual(self.alertas()['cantidad'], 0)

    def test_variantes_ajenas_no_aparecen(self):
        producto = Producto.objects.create(tienda=self.ajena, nombre='Secreto')
        Variante.objects.create(producto=producto, sku='SECRETO', precio=1, stock=0)
        self.assertEqual(self.alertas()['cantidad'], 1)
        self.assertEqual(self.panel()['productos_bajo_stock'], 1)

    def test_cantidad_correcta_sin_duplicados(self):
        Variante.objects.create(producto=self.producto, sku='ROJO', precio=1, stock=0)
        data = self.alertas()
        ids = [a['variante_id'] for a in data['alertas_stock']]
        self.assertEqual(data['cantidad'], 2)
        self.assertEqual(len(set(ids)), 2)

    def test_reposicion_por_api_desaparece_en_consulta_siguiente(self):
        url = reverse('variante-inventario', kwargs={
            'tienda_id': self.tienda.pk, 'producto_id': self.producto.pk,
            'variante_id': self.variante.pk,
        })
        response = self.client.patch(url, {'stock': 6, 'stock_esperado': 3}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.alertas()['cantidad'], 0)

    def test_venta_trigger_reduce_stock_y_aparece(self):
        self.stock(6)
        self.assertEqual(self.alertas()['cantidad'], 0)
        pedido = self.pedido(estado='procesado')
        ItemPedido.objects.create(
            tienda=self.tienda, pedido=pedido, variante=self.variante,
            cantidad=3, precio_unitario='10.00',
        )
        self.variante.refresh_from_db()
        self.assertEqual(self.variante.stock, 3)
        self.assertEqual(self.alertas()['cantidad'], 1)

    @override_settings(STRIPE_SECRET_KEY='sk_test_mock_cu17')
    @patch('apps.pedidos.views.stripe.PaymentIntent.retrieve')
    def test_checkout_pago_confirmado_refleja_alertas_y_unidades(self, retrieve):
        self.stock(6)
        carrito = Carrito.objects.create(cliente=self.cliente, tienda=self.tienda)
        ItemCarrito.objects.create(tienda=self.tienda, carrito=carrito, variante=self.variante, cantidad=3)
        retrieve.return_value = SimpleNamespace(status='succeeded', amount=_usd_centavos(Decimal('30.00')))
        self.client.force_authenticate(self.cliente)
        response = self.client.post(reverse('carrito_checkout'), {
            'metodo_pago': 'stripe', 'payment_intent_id': 'pi_cu17_confirmado',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        pedido = Pedido.objects.get(pk=response.data['pedidos'][0])
        self.assertEqual(pedido.pagos.get().estado, 'pagado')
        self.client.force_authenticate(self.empresa)
        self.assertEqual(self.alertas()['alertas_stock'][0]['stock'], 3)
        self.assertEqual(self.panel()['ventas_semana'][-1]['cantidad'], 3)

    def test_sin_alertas_contrato_vacio(self):
        self.stock(5)
        self.assertEqual(self.alertas(), {'tienda_id': self.tienda.pk, 'cantidad': 0, 'alertas_stock': []})

    def test_ajena_e_inexistente_misma_respuesta_sin_datos(self):
        for endpoint in ['dashboard_tienda', 'alertas_stock']:
            with self.subTest(endpoint=endpoint):
                ajena = self.client.get(self.url(endpoint, self.ajena))
                inexistente = self.client.get(reverse(endpoint, kwargs={'tienda_id': 999999}))
                self.assertEqual(ajena.status_code, 404)
                self.assertEqual(ajena.data, inexistente.data)
                self.assertNotIn('tienda', ajena.data)

    def test_no_autenticado_rechazado(self):
        self.client.force_authenticate(None)
        for endpoint in ['dashboard_tienda', 'alertas_stock']:
            self.assertEqual(self.client.get(self.url(endpoint)).status_code, 401)

    def test_rol_incorrecto_rechazado(self):
        self.client.force_authenticate(self.cliente)
        for endpoint in ['dashboard_tienda', 'alertas_stock']:
            self.assertEqual(self.client.get(self.url(endpoint)).status_code, 403)

    def test_productos_totales_y_activos(self):
        Producto.objects.create(tienda=self.tienda, nombre='Inactivo', activo=False)
        Producto.objects.create(tienda=self.ajena, nombre='Ajeno')
        data = self.panel()
        self.assertEqual(data['total_productos'], 2)
        self.assertEqual(data['productos_activos'], 1)
        self.assertEqual(data['tienda']['nombre'], self.tienda.nombre)

    def test_pedidos_totales_y_pendientes(self):
        self.pedido()
        self.pedido(estado='procesado')
        self.pedido(estado='cancelado')
        self.pedido(tienda=self.ajena)
        data = self.panel()
        self.assertEqual(data['total_pedidos'], 3)
        self.assertEqual(data['pedidos_pendientes'], 1)

    def test_stock_bajo_panel_igual_endpoint(self):
        self.assertEqual(self.panel()['productos_bajo_stock'], self.alertas()['cantidad'])
        self.assertEqual(self.panel()['alertas_stock'], self.alertas()['alertas_stock'])

    def test_importe_decimal_excluye_cancelados_y_ajenos(self):
        self.pedido(total='10.25')
        self.pedido(total='20.10', estado='entregado')
        self.pedido(total='900.00', estado='cancelado')
        self.pedido(total='700.00', tienda=self.ajena)
        self.assertEqual(self.panel()['ingresos_totales'], '30.35')

    def test_importe_sin_pedidos_cero_decimal(self):
        self.assertEqual(self.panel()['ingresos_totales'], '0.00')

    def test_grafico_siete_fechas_consecutivas_ordenadas_incluye_hoy(self):
        fechas = [dia['fecha'] for dia in self.panel()['ventas_semana']]
        esperado = [(timezone.localdate() - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
        self.assertEqual(fechas, esperado)

    def test_grafico_completa_ceros(self):
        self.pedido(cantidad=4, dias=2)
        cantidades = [dia['cantidad'] for dia in self.panel()['ventas_semana']]
        self.assertEqual(cantidades, [0, 0, 0, 0, 4, 0, 0])

    def test_grafico_suma_items_no_pedidos(self):
        self.pedido(cantidad=4)
        self.pedido(cantidad=7)
        self.assertEqual(self.panel()['ventas_semana'][-1]['cantidad'], 11)

    def test_grafico_excluye_cancelados_ajenos_y_fuera_periodo(self):
        self.pedido(cantidad=4, estado='cancelado')
        self.pedido(cantidad=7, tienda=self.ajena)
        self.pedido(cantidad=6, dias=7)
        self.pedido(cantidad=2, dias=-1)
        self.assertEqual(sum(dia['cantidad'] for dia in self.panel()['ventas_semana']), 0)

    def test_grafico_usa_fecha_local_no_utc(self):
        pedido = self.pedido(cantidad=3)
        madrugada = timezone.make_aware(datetime.combine(timezone.localdate(), time(23, 30)))
        Pedido.objects.filter(pk=pedido.pk).update(fecha=madrugada)
        self.assertEqual(self.panel()['ventas_semana'][-1]['cantidad'], 3)

    def test_dos_tiendas_propias_no_mezclan(self):
        self.pedido(cantidad=3)
        self.pedido(cantidad=8, tienda=self.segunda)
        data = self.panel(self.segunda)
        self.assertEqual(data['total_productos'], 1)
        self.assertEqual(data['total_pedidos'], 1)
        self.assertEqual(data['productos_bajo_stock'], 0)
        self.assertEqual(data['ingresos_totales'], '82.00')
        self.assertEqual(data['ventas_semana'][-1]['cantidad'], 8)

    def test_ruta_legacy_exige_seleccion_con_varias_tiendas(self):
        url = reverse('dashboard_vendedor')
        self.assertEqual(self.client.get(url).status_code, 400)
        self.assertEqual(self.client.get(url, {'tienda_id': self.ajena.pk}).status_code, 404)
        self.assertEqual(self.client.get(url, {'tienda_id': self.tienda.pk}).status_code, 200)
        self.assertEqual(self.client.get(url, {'tienda_id': 'abc'}).status_code, 400)

    def test_consultas_constantes_sin_n_mas_uno(self):
        for i in range(10):
            Variante.objects.create(producto=self.producto, sku=f'BAJO-{i}', precio=1, stock=0)
        with self.assertNumQueries(4):
            data = consultar_panel_tienda(self.tienda)
        self.assertEqual(data['productos_bajo_stock'], 11)

    def test_relaciones_secundarias_inconsistentes_no_filtran_datos(self):
        pedido = self.pedido(cantidad=2)
        pedido.items.update(tienda=self.ajena)
        self.assertEqual(sum(d['cantidad'] for d in self.panel()['ventas_semana']), 0)
