from datetime import timedelta
from decimal import Decimal
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APITestCase
from apps.usuarios.models import Rol, Usuario
from apps.tiendas.models import Tienda
from apps.catalogo.models import Producto, Variante
from apps.pedidos.models import Carrito, ItemCarrito
from .models import CampanaCarrito, RegistroRecuperacionCarrito
from io import StringIO


class CampanaMovilTests(APITestCase):
    def setUp(self):
        empresa = Rol.objects.get_or_create(nombre='empresa')[0]
        cliente = Rol.objects.get_or_create(nombre='cliente')[0]
        self.empresa = Usuario.objects.create_user(email='empresa@example.test', password='prueba', rol=empresa)
        self.otra = Usuario.objects.create_user(email='otra@example.test', password='prueba', rol=empresa)
        self.cliente = Usuario.objects.create_user(email='cliente@example.test', password='prueba', rol=cliente)
        self.tienda = Tienda.objects.create(propietario=self.empresa, nombre='Tienda prueba')
        self.ajena = Tienda.objects.create(propietario=self.otra, nombre='Otra tienda')
        self.campana = CampanaCarrito.objects.create(tienda=self.tienda, activo=True, horas_inactividad=2)
        self.carrito = Carrito.objects.create(cliente=self.cliente, tienda=self.tienda)
        producto = Producto.objects.create(tienda=self.tienda, nombre='Producto', slug='producto')
        variante = Variante.objects.create(producto=producto, sku='TEST-CU26', precio=Decimal('20'), stock=10)
        self.item = ItemCarrito.objects.create(carrito=self.carrito, tienda=self.tienda, variante=variante)
        self.path = f'/api/tiendas/{self.tienda.id}/campana-carrito/'

    def test_empresa_solo_accede_a_su_tienda_y_cliente_no_configura(self):
        self.client.force_authenticate(self.empresa)
        self.assertEqual(self.client.get(self.path).status_code, 200)
        self.assertEqual(self.client.get(f'/api/tiendas/{self.ajena.id}/campana-carrito/').status_code, 404)
        self.client.force_authenticate(self.cliente)
        self.assertEqual(self.client.get(self.path).status_code, 403)

    def test_actividad_reciente_evitar_falso_abandono(self):
        Carrito.objects.filter(pk=self.carrito.id).update(fecha_creacion=timezone.now()-timedelta(days=10))
        self.client.force_authenticate(self.empresa)
        respuesta = self.client.get(self.path)
        self.assertEqual(respuesta.data['metricas']['carritos_detectados'], 0)
        Carrito.objects.filter(pk=self.carrito.id).update(ultima_actividad=timezone.now()-timedelta(hours=4))
        self.assertEqual(self.client.get(self.path).data['metricas']['carritos_detectados'], 1)
        self.item.cantidad = 2
        self.item.save()
        self.assertEqual(self.client.get(self.path).data['metricas']['carritos_detectados'], 0)

    def test_limites_invalidos_no_modifican_la_campana(self):
        self.client.force_authenticate(self.empresa)
        self.assertEqual(self.client.patch(self.path, {'horas_inactividad': 0}, format='json').status_code, 400)
        self.campana.refresh_from_db()
        self.assertEqual(self.campana.horas_inactividad, 2)

    def test_dry_run_no_envia_ni_registra_notificaciones(self):
        Carrito.objects.filter(pk=self.carrito.id).update(ultima_actividad=timezone.now()-timedelta(hours=4))
        call_command('procesar_carritos_abandonados', dry_run=True, stdout=StringIO())
        self.assertEqual(RegistroRecuperacionCarrito.objects.count(), 0)

    def test_checkout_marca_recuperacion_del_cliente_sin_afectar_otras(self):
        registro = RegistroRecuperacionCarrito.objects.create(campana=self.campana, carrito=self.carrito, cliente=self.cliente)
        self.client.force_authenticate(self.cliente)
        respuesta = self.client.post('/api/pedidos/carrito/checkout/', {'metodo_pago': 'efectivo'}, format='json')
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        registro.refresh_from_db()
        self.assertTrue(registro.recuperado)
        self.assertIsNotNone(registro.pedido_resultante_id)
