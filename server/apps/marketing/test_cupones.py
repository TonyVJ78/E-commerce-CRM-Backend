import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from apps.usuarios.models import Rol, Usuario
from apps.tiendas.models import Tienda
from apps.catalogo.models import Producto, Variante
from apps.crm.models import Segmento, FichaCliente
from apps.pedidos.models import Carrito, ItemCarrito, Pedido, Pago
from .models import Cupon, CuponUso


class CuponesTests(APITestCase):
    def setUp(self):
        empresa = Rol.objects.get_or_create(nombre='empresa')[0]
        cliente = Rol.objects.get_or_create(nombre='cliente')[0]
        self.empresa = Usuario.objects.create_user(email='empresa@example.test', password='prueba', rol=empresa)
        self.otra = Usuario.objects.create_user(email='otra@example.test', password='prueba', rol=empresa)
        self.cliente = Usuario.objects.create_user(email='cliente@example.test', password='prueba', rol=cliente)
        self.otro_cliente = Usuario.objects.create_user(email='otro@example.test', password='prueba', rol=cliente)
        self.tienda = Tienda.objects.create(propietario=self.empresa, nombre='Prueba cupones')
        self.ajena = Tienda.objects.create(propietario=self.otra, nombre='Tienda ajena')
        producto = Producto.objects.create(tienda=self.tienda, nombre='Producto', slug='producto')
        self.variante = Variante.objects.create(producto=producto, sku='CU27-TEST', precio=Decimal('20'), stock=20)
        self.carrito = Carrito.objects.create(tienda=self.tienda, cliente=self.cliente)
        ItemCarrito.objects.create(carrito=self.carrito, tienda=self.tienda, variante=self.variante, cantidad=2)
        self.cupon = Cupon.objects.create(tienda=self.tienda, codigo='AHORRA25', tipo_descuento='porcentaje',
            valor_descuento=25, fecha_expiracion=timezone.localdate()+timedelta(days=7), usos_maximos=5)
        self.path = f'/api/tiendas/{self.tienda.id}/cupones/'
        self.client.force_authenticate(self.cliente)

    def validar(self, codigo=None, tienda=None):
        return self.client.post('/api/marketing/cupones/validar/', {
            'tienda_id': tienda or self.tienda.id, 'codigo': codigo or self.cupon.codigo,
        }, format='json')

    def test_cotiza_en_servidor_sin_consumir_usos(self):
        respuesta = self.validar('ahorra25')
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(respuesta.data['subtotal'], '40.00')
        self.assertEqual(respuesta.data['descuento'], '10.00')
        self.assertEqual(respuesta.data['total'], '30.00')
        self.assertEqual(CuponUso.objects.count(), 0)

    def test_no_permite_cupon_de_otra_tienda_ni_carrito_de_otro_cliente(self):
        self.assertEqual(self.validar(tienda=self.ajena.id).status_code, 400)
        self.client.force_authenticate(self.otro_cliente)
        self.assertEqual(self.validar().status_code, 400)

    def test_expiracion_minimo_inactividad_y_cupo_se_validan(self):
        for cambios in ({'activo': False}, {'monto_minimo': 50}, {'fecha_expiracion': timezone.localdate()-timedelta(days=1)}, {'usos_maximos': 0}):
            originales = {campo: getattr(self.cupon, campo) for campo in cambios}
            Cupon.objects.filter(pk=self.cupon.id).update(**cambios)
            self.assertEqual(self.validar().status_code, 400, cambios)
            Cupon.objects.filter(pk=self.cupon.id).update(**originales)

    def test_segmento_solo_permite_destinatarios_de_la_misma_tienda(self):
        segmento = Segmento.objects.create(tienda=self.tienda, nombre='VIP', criterio='Alto valor')
        self.cupon.segmento_objetivo = segmento; self.cupon.save()
        self.assertEqual(self.validar().status_code, 400)
        FichaCliente.objects.create(tienda=self.tienda, cliente=self.cliente, segmento=segmento)
        self.assertEqual(self.validar().status_code, 200)

    def test_checkout_preserva_subtotal_aplica_descuento_y_pago_real(self):
        res = self.client.post('/api/pedidos/carrito/checkout/', {
            'metodo_pago': 'efectivo', 'cupones': {str(self.tienda.id): 'AHORRA25'},
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        pedido = Pedido.objects.get(pk=res.data['pedidos'][0])
        self.assertEqual(pedido.subtotal, Decimal('40'))
        self.assertEqual(pedido.total, Decimal('30'))
        self.assertEqual(Pago.objects.get(pedido=pedido).monto, Decimal('30'))
        self.assertEqual(CuponUso.objects.filter(pedido=pedido, cupon=self.cupon).count(), 1)
        self.variante.refresh_from_db()
        self.assertEqual(self.variante.stock, 18)
        ItemCarrito.objects.create(carrito=self.carrito, tienda=self.tienda, variante=self.variante)
        self.assertEqual(self.validar().status_code, 400)

    def test_empresa_crea_solo_en_su_tienda_y_no_acepta_segmentos_ajenos(self):
        self.assertEqual(self.client.get(self.path).status_code, 403)
        self.client.force_authenticate(self.empresa)
        payload={'codigo': 'NUEVO10', 'tipo_descuento': 'monto_fijo', 'valor_descuento': '10',
                 'fecha_expiracion': str(timezone.localdate()+timedelta(days=5)), 'usos_maximos': 20}
        self.assertEqual(self.client.post(self.path, payload, format='json').status_code, 201)
        self.assertEqual(self.client.post(self.path, payload, format='json').status_code, 400)
        self.assertEqual(self.client.post(f'/api/tiendas/{self.ajena.id}/cupones/', payload, format='json').status_code, 404)
        segmento = Segmento.objects.create(tienda=self.ajena, nombre='Ajeno', criterio='Prueba')
        self.assertEqual(self.client.post(self.path, {**payload, 'codigo':'OTRO10', 'segmento_id': segmento.id}, format='json').status_code, 400)

    @override_settings(STRIPE_SECRET_KEY='clave-simulada-sin-valor')
    def test_activar_solo_modifica_el_cupon_de_la_tienda_del_propietario(self):
        self.client.force_authenticate(self.empresa)
        detalle = f'{self.path}{self.cupon.id}/'
        self.assertEqual(self.client.get(detalle).status_code, 405)
        res = self.client.patch(detalle, {'activo': False}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.cupon.refresh_from_db()
        self.assertFalse(self.cupon.activo)
        self.assertEqual(self.client.patch(f'/api/tiendas/{self.ajena.id}/cupones/{self.cupon.id}/', {'activo': True}, format='json').status_code, 404)

    @override_settings(STRIPE_SECRET_KEY='clave-simulada-sin-valor')
    @patch('apps.pedidos.views.stripe.PaymentIntent.create')
    def test_intento_stripe_usa_el_total_descontado_y_vincula_cupones(self, crear):
        crear.return_value = SimpleNamespace(client_secret='simulado', id='pi_simulado')
        res=self.client.post('/api/pedidos/carrito/pago-intento/', {'cupones':{str(self.tienda.id):'AHORRA25'}}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['monto_bs'], '30.00')
        self.assertEqual(crear.call_args.kwargs['metadata']['cupones'], json.dumps({str(self.tienda.id): 'AHORRA25'}, sort_keys=True))


    def test_cupon_segmentado_reconoce_clasificacion_automatica_cu24(self):
        from apps.crm.models import ReglaSegmentacion
        from apps.crm.services.segmentacion_service import recalcular_segmentos_tienda
        ReglaSegmentacion.objects.create(tienda=self.tienda, min_compras_frecuente=1)
        Pedido.objects.create(cliente=self.cliente, tienda=self.tienda, estado_actual='entregado', subtotal=40, total=40)
        recalcular_segmentos_tienda(self.tienda)
        segmento = Segmento.objects.get(tienda=self.tienda, criterio='rfm:FRECUENTE')
        self.cupon.segmento_objetivo = segmento
        self.cupon.save()
        self.assertEqual(self.validar().status_code, 200)
        self.client.force_authenticate(self.otro_cliente)
        self.assertEqual(self.validar().status_code, 400)
