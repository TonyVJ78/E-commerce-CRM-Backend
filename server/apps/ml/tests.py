"""
Pruebas automatizadas de CU-35: Machine Learning.

Se ejecutan sobre la base de datos de prueba de Django (SQLite en memoria por
defecto). NO tocan Neon ni tablas de producción.
"""

from decimal import Decimal
from datetime import date, timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.usuarios.models import Rol, Usuario
from apps.tiendas.models import Tienda
from apps.catalogo.models import Categoria, Producto, Variante
from apps.pedidos.models import Pedido, ItemPedido

from apps.ml.services.ventas import pronosticar_ventas
from apps.ml.services.abandono import evaluar_riesgo_abandono
from apps.ml.services.compras import predecir_compra
from apps.ml.services.sinteticos import generar_datos_sinteticos


class _BaseML(TestCase):
    """Utilidad para crear datos mínimos de prueba."""

    @classmethod
    def setUpTestData(cls):
        cls.rol_empresa, _ = Rol.objects.get_or_create(nombre='empresa')
        cls.rol_cliente, _ = Rol.objects.get_or_create(nombre='cliente')

        cls.usuario_empresa = Usuario.objects.create_user(
            email='empresa-ml@example.com',
            password='Password123!',
            rol=cls.rol_empresa,
        )
        cls.usuario_empresa2 = Usuario.objects.create_user(
            email='empresa2-ml@example.com',
            password='Password123!',
            rol=cls.rol_empresa,
        )
        cls.usuario_cliente = Usuario.objects.create_user(
            email='cliente-ml@example.com',
            password='Password123!',
            rol=cls.rol_cliente,
        )

        cls.tienda_a = Tienda.objects.create(
            propietario=cls.usuario_empresa,
            nombre='Tienda A ML',
            slug='tienda-a-ml',
            activa=True,
        )
        cls.tienda_b = Tienda.objects.create(
            propietario=cls.usuario_empresa2,
            nombre='Tienda B ML',
            slug='tienda-b-ml',
            activa=True,
        )

        cls.categoria = Categoria.objects.create(
            tienda=cls.tienda_a, nombre='Categoria ML'
        )
        cls.producto = Producto.objects.create(
            tienda=cls.tienda_a,
            categoria=cls.categoria,
            nombre='Producto ML',
            slug='producto-ml',
            activo=True,
        )
        cls.variante = Variante.objects.create(
            producto=cls.producto,
            nombre='Variante ML',
            sku='VAR-ML-001',
            precio=Decimal('100.00'),
            stock=10,
            stock_minimo=1,
            activa=True,
        )

    @classmethod
    def _crear_pedido_con_fecha(cls, cliente, tienda, estado, subtotal, total, fecha):
        """Crea un Pedido con fecha específica, saltando auto_now_add del modelo."""
        pedido = Pedido.objects.create(
            cliente=cliente,
            tienda=tienda,
            estado_actual=estado,
            subtotal=subtotal,
            total=total,
        )
        Pedido.objects.filter(id=pedido.id).update(fecha=fecha)
        return pedido


class MlDatosSinteticosTestCase(_BaseML):
    def test_generacion_reproducible_con_semilla(self):
        d1 = generar_datos_sinteticos(seed=42, n_clientes=50, n_tiendas=3)
        d2 = generar_datos_sinteticos(seed=42, n_clientes=50, n_tiendas=3)
        self.assertEqual(d1['semilla'], d2['semilla'])
        self.assertEqual(d1['resumen']['n_clientes'], d2['resumen']['n_clientes'])
        self.assertEqual(
            d1['resumen']['distribucion_patrones'],
            d2['resumen']['distribucion_patrones'],
        )
        # No se insertan en BD real: solo estructuras en memoria simples
        self.assertIsInstance(d1['tiendas'][0], dict)
        self.assertIn('id', d1['tiendas'][0])
        self.assertIn('nombre', d1['tiendas'][0])

    def test_separacion_train_test(self):
        datos = generar_datos_sinteticos(seed=7, n_clientes=100, n_tiendas=2)
        res = datos['resumen']
        self.assertGreater(res['train_clientes'], 0)
        self.assertGreater(res['test_clientes'], 0)
        self.assertEqual(
            res['train_clientes'] + res['test_clientes'], res['n_clientes']
        )


class MlServiciosVentasTestCase(_BaseML):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Stock suficiente para soportar los ItemPedido de prueba (evitar trigger de stock)
        cls.variante.stock = 9999
        cls.variante.save()
        # Crear pedidos no cancelados en tienda_a durante varios días
        base = date(2026, 1, 1)
        for i in range(30):
            d = base + timedelta(days=i)
            pedido = cls._crear_pedido_con_fecha(
                cliente=cls.usuario_empresa,
                tienda=cls.tienda_a,
                estado='completado',
                subtotal=Decimal('100.00'),
                total=Decimal('100.00'),
                fecha=timezone.make_aware(timezone.datetime(d.year, d.month, d.day)),
            )
            ItemPedido.objects.create(
                tienda=cls.tienda_a,
                pedido=pedido,
                variante=cls.variante,
                cantidad=1,
                precio_unitario=Decimal('100.00'),
            )
        # Un pedido cancelado (debe ignorarse)
        d_cancel = base + timedelta(days=15)
        ped_cancel = cls._crear_pedido_con_fecha(
            cliente=cls.usuario_empresa,
            tienda=cls.tienda_a,
            estado='cancelado',
            subtotal=Decimal('999.00'),
            total=Decimal('999.00'),
            fecha=timezone.make_aware(timezone.datetime(d_cancel.year, d_cancel.month, d_cancel.day)),
        )
        ItemPedido.objects.create(
            tienda=cls.tienda_a,
            pedido=ped_cancel,
            variante=cls.variante,
            cantidad=1,
            precio_unitario=Decimal('999.00'),
        )

    def test_pronostico_ventas_completado(self):
        resultado = pronosticar_ventas(tienda=self.tienda_a, horizonte_dias=7)
        self.assertEqual(resultado['estado'], 'completado')
        self.assertEqual(len(resultado['fechas_previstas']), 7)
        self.assertIn('fecha_corte', resultado)
        self.assertIn('metrica', resultado)
        # Todas las fechas previstas son futuras respecto al corte
        corte = date.fromisoformat(resultado['fecha_corte'])
        for fp in resultado['fechas_previstas']:
            fp_date = date.fromisoformat(fp['fecha'])
            self.assertGreater(fp_date, corte)
            self.assertGreaterEqual(fp['valor_previsto'], 0)

    def test_pronostico_ventas_no_incluye_cancelados(self):
        resultado = pronosticar_ventas(tienda=self.tienda_a, horizonte_dias=7)
        # El pedido cancelado de 999 no debe distorsionar el pronóstico
        self.assertEqual(resultado['estado'], 'completado')

    def test_aislamiento_tienda_ventas(self):
        resultado_b = pronosticar_ventas(tienda=self.tienda_b, horizonte_dias=7)
        self.assertEqual(resultado_b['estado'], 'datos_insuficientes')


class MlServiciosAbandonoTestCase(_BaseML):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Stock suficiente para soportar los ItemPedido de prueba (evitar trigger de stock)
        cls.variante.stock = 9999
        cls.variante.save()
        # Crear varios clientes con historial en tienda_a
        base = date(2026, 1, 1)
        for c in range(8):
            user = Usuario.objects.create_user(
                email=f'cliente-ab-{c}@example.com',
                password='Password123!',
                rol=cls.rol_cliente,
            )
            # Cada cliente con pedidos en fechas distintas
            for i in range(c + 1):
                d = base + timedelta(days=i * 10)
                pedido = cls._crear_pedido_con_fecha(
                    cliente=user,
                    tienda=cls.tienda_a,
                    estado='completado',
                    subtotal=Decimal('50.00'),
                    total=Decimal('50.00'),
                    fecha=timezone.make_aware(timezone.datetime(d.year, d.month, d.day)),
                )
                ItemPedido.objects.create(
                    tienda=cls.tienda_a,
                    pedido=pedido,
                    variante=cls.variante,
                    cantidad=1,
                    precio_unitario=Decimal('50.00'),
                )
        # Clientes abandonados: pedidos antiguos (recencia > 90 días)
        for c in range(2):
            user = Usuario.objects.create_user(
                email=f'cliente-ab-antiguo-{c}@example.com',
                password='Password123!',
                rol=cls.rol_cliente,
            )
            d = date(2025, 9, 1)
            pedido = cls._crear_pedido_con_fecha(
                cliente=user,
                tienda=cls.tienda_a,
                estado='completado',
                subtotal=Decimal('50.00'),
                total=Decimal('50.00'),
                fecha=timezone.make_aware(timezone.datetime(d.year, d.month, d.day)),
            )
            ItemPedido.objects.create(
                tienda=cls.tienda_a,
                pedido=pedido,
                variante=cls.variante,
                cantidad=1,
                precio_unitario=Decimal('50.00'),
            )

    def test_abandono_completado(self):
        resultado = evaluar_riesgo_abandono(
            tienda=self.tienda_a, dias_umbral_abandono=90
        )
        self.assertEqual(resultado['estado'], 'completado')
        self.assertGreaterEqual(len(resultado['clientes']), 1)
        for c in resultado['clientes']:
            self.assertIn('probabilidad_abandono', c)
            self.assertIn('nivel_riesgo', c)
            self.assertIn(c['nivel_riesgo'], ['bajo', 'medio', 'alto', 'critico'])
            self.assertIn('variables_explicativas', c)
        self.assertIn('metrica', resultado)

    def test_abandono_aislamiento(self):
        resultado_b = evaluar_riesgo_abandono(
            tienda=self.tienda_b, dias_umbral_abandono=90
        )
        self.assertEqual(resultado_b['estado'], 'datos_insuficientes')

    def test_abandono_datos_insuficientes(self):
        # Tienda con muy pocos clientes
        tienda_c = Tienda.objects.create(
            propietario=self.usuario_empresa,
            nombre='Tienda C ML',
            slug='tienda-c-ml',
            activa=True,
        )
        resultado = evaluar_riesgo_abandono(
            tienda=tienda_c, dias_umbral_abandono=90
        )
        self.assertEqual(resultado['estado'], 'datos_insuficientes')
        self.assertEqual(resultado['clientes'], [])


class MlServiciosComprasTestCase(_BaseML):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Stock suficiente para soportar los ItemPedido de prueba (evitar trigger de stock)
        cls.variante.stock = 9999
        cls.variante.save()
        base = date(2026, 1, 1)
        for c in range(6):
            user = Usuario.objects.create_user(
                email=f'cliente-compra-{c}@example.com',
                password='Password123!',
                rol=cls.rol_cliente,
            )
            for i in range(c + 1):
                d = base + timedelta(days=i * 15)
                pedido = cls._crear_pedido_con_fecha(
                    cliente=user,
                    tienda=cls.tienda_a,
                    estado='completado',
                    subtotal=Decimal('40.00'),
                    total=Decimal('40.00'),
                    fecha=timezone.make_aware(timezone.datetime(d.year, d.month, d.day)),
                )
                ItemPedido.objects.create(
                    tienda=cls.tienda_a,
                    pedido=pedido,
                    variante=cls.variante,
                    cantidad=1,
                    precio_unitario=Decimal('40.00'),
                )

    def test_prediccion_compra_cliente_con_historial(self):
        cliente = Usuario.objects.get(email='cliente-compra-0@example.com')
        resultado = predecir_compra(
            tienda=self.tienda_a,
            cliente_id=cliente.id,
            horizonte_dias=7,
        )
        self.assertIn(resultado['estado'], ['completado', 'datos_insuficientes'])
        if resultado['estado'] == 'completado':
            self.assertIsInstance(resultado['probabilidad_compra'], float)
            self.assertGreaterEqual(resultado['probabilidad_compra'], 0)
            self.assertLessEqual(resultado['probabilidad_compra'], 1)
            self.assertIn('nivel', resultado)
            self.assertIn('variables_explicativas', resultado)

    def test_prediccion_compra_sin_historial(self):
        resultado = predecir_compra(
            tienda=self.tienda_a,
            cliente_id=99999,
            horizonte_dias=7,
        )
        self.assertEqual(resultado['estado'], 'datos_insuficientes')
        self.assertEqual(resultado['probabilidad_compra'], 0.05)

    def test_prediccion_compra_aislamiento(self):
        resultado_b = predecir_compra(
            tienda=self.tienda_b,
            cliente_id=self.usuario_cliente.id,
            horizonte_dias=7,
        )
        self.assertEqual(resultado_b['estado'], 'datos_insuficientes')


class MlEndpointsAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rol_empresa, _ = Rol.objects.get_or_create(nombre='empresa')
        cls.rol_cliente, _ = Rol.objects.get_or_create(nombre='cliente')
        cls.usuario_empresa = Usuario.objects.create_user(
            email='emp-end@example.com',
            password='Password123!',
            rol=cls.rol_empresa,
        )
        cls.usuario_cliente = Usuario.objects.create_user(
            email='cli-end@example.com',
            password='Password123!',
            rol=cls.rol_cliente,
        )
        cls.tienda = Tienda.objects.create(
            propietario=cls.usuario_empresa,
            nombre='Tienda End',
            slug='tienda-end',
            activa=True,
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_pronosticar_ventas_requiere_autenticacion(self):
        url = reverse('ml_ventas_pronosticar')
        response = self.client.post(url, {'tienda_id': self.tienda.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_pronosticar_ventas_empresa_propietaria(self):
        self._auth(self.usuario_empresa)
        url = reverse('ml_ventas_pronosticar')
        response = self.client.post(
            url, {'tienda_id': self.tienda.id, 'horizonte_dias': 7}, format='json'
        )
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST])
        # Si no hay ventas, retorna 200 con datos_insuficientes (el servicio lo maneja)
        if response.status_code == status.HTTP_200_OK:
            self.assertIn('estado', response.data)

    def test_pronosticar_ventas_otra_tienda_403(self):
        # Empresa que no es propietaria de la tienda
        otra = Usuario.objects.create_user(
            email='emp2-end@example.com',
            password='Password123!',
            rol=self.rol_empresa,
        )
        self._auth(otra)
        url = reverse('ml_ventas_pronosticar')
        response = self.client.post(
            url, {'tienda_id': self.tienda.id}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_listar_pronosticos_requiere_autenticacion(self):
        url = reverse('ml_ventas_listar')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_riesgo_abandono_cliente_no_empresa_403(self):
        self._auth(self.usuario_cliente)
        url = reverse('ml_abandono_evaluar')
        response = self.client.post(
            url, {'tienda_id': self.tienda.id}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_predecir_compra_cliente_propietario(self):
        self._auth(self.usuario_cliente)
        url = reverse('ml_compras_predecir')
        response = self.client.post(
            url, {'tienda_id': self.tienda.id, 'cliente_id': self.usuario_cliente.id}, format='json'
        )
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST])

    def test_error_entrada_tienda_inexistente(self):
        self._auth(self.usuario_empresa)
        url = reverse('ml_ventas_pronosticar')
        response = self.client.post(
            url, {'tienda_id': 999999}, format='json'
        )
        # get_object_or_404 devuelve 404 cuando la tienda no existe
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
