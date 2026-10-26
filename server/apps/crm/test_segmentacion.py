from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.crm.models import (
    ReglaSegmentacion,
    SegmentoCliente,
)
from apps.crm.services.segmentacion_service import recalcular_segmentos_tienda
from apps.marketing.models import NotificacionEnviada
from apps.pedidos.models import MetodoPago, Pago, Pedido
from apps.tiendas.models import Tienda
from apps.usuarios.models import Rol, Usuario


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class SegmentacionClientesTests(TestCase):
    def setUp(self):
        self.rol_empresa, _ = Rol.objects.get_or_create(nombre='empresa')
        self.rol_cliente, _ = Rol.objects.get_or_create(nombre='cliente')
        self.empresa = Usuario.objects.create_user(
            email='empresa@example.com',
            password='test-password',
            rol=self.rol_empresa,
        )
        self.cliente_frecuente = self.crear_cliente('frecuente@example.com')
        self.cliente_alto_valor = self.crear_cliente('alto@example.com')
        self.cliente_inactivo = self.crear_cliente('inactivo@example.com')
        self.otro_cliente = self.crear_cliente('otro@example.com')
        self.tienda = Tienda.objects.create(propietario=self.empresa, nombre='Tienda A')
        self.otra_empresa = Usuario.objects.create_user(
            email='otra-empresa@example.com',
            password='test-password',
            rol=self.rol_empresa,
        )
        self.otra_tienda = Tienda.objects.create(
            propietario=self.otra_empresa,
            nombre='Tienda B',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.empresa)

    def crear_cliente(self, email):
        return Usuario.objects.create_user(
            email=email,
            password='test-password',
            rol=self.rol_cliente,
            first_name=email.split('@')[0],
        )

    def crear_pedido(self, cliente, tienda=None, total='100.00', fecha=None):
        pedido = Pedido.objects.create(
            cliente=cliente,
            tienda=tienda or self.tienda,
            estado_actual='entregado',
            subtotal=Decimal(total),
            total=Decimal(total),
        )
        if fecha:
            Pedido.objects.filter(pk=pedido.pk).update(fecha=fecha)
        return pedido

    def test_recalculo_clasifica_por_frecuencia_valor_y_recencia(self):
        for _ in range(3):
            self.crear_pedido(self.cliente_frecuente)
        self.crear_pedido(self.cliente_alto_valor, total='1200.00')
        self.crear_pedido(
            self.cliente_inactivo,
            fecha=timezone.now() - timedelta(days=61),
        )

        resumen = recalcular_segmentos_tienda(self.tienda)

        self.assertEqual(
            SegmentoCliente.objects.get(tienda=self.tienda, cliente=self.cliente_frecuente).segmento,
            SegmentoCliente.FRECUENTE,
        )
        self.assertEqual(
            SegmentoCliente.objects.get(tienda=self.tienda, cliente=self.cliente_alto_valor).segmento,
            SegmentoCliente.ALTO_VALOR,
        )
        inactivo = SegmentoCliente.objects.get(tienda=self.tienda, cliente=self.cliente_inactivo)
        self.assertEqual(inactivo.segmento, SegmentoCliente.INACTIVO)
        self.assertEqual(inactivo.total_compras, 1)
        self.assertEqual(resumen['total_clientes'], 3)

    def test_recalculo_cuenta_pedidos_pagados_y_excluye_cancelados(self):
        metodo = MetodoPago.objects.create(nombre='Tarjeta')
        pedido_pagado = Pedido.objects.create(
            cliente=self.cliente_frecuente,
            tienda=self.tienda,
            estado_actual='pendiente',
            subtotal=Decimal('50.00'),
            total=Decimal('50.00'),
        )
        Pago.objects.create(
            tienda=self.tienda,
            pedido=pedido_pagado,
            metodo_pago=metodo,
            monto=Decimal('50.00'),
            estado='pagado',
        )
        pedido_cancelado = Pedido.objects.create(
            cliente=self.cliente_alto_valor,
            tienda=self.tienda,
            estado_actual='cancelado',
            subtotal=Decimal('1200.00'),
            total=Decimal('1200.00'),
        )
        Pago.objects.create(
            tienda=self.tienda,
            pedido=pedido_cancelado,
            metodo_pago=metodo,
            monto=Decimal('1200.00'),
            estado='pagado',
        )

        recalcular_segmentos_tienda(self.tienda)

        self.assertTrue(
            SegmentoCliente.objects.filter(
                tienda=self.tienda,
                cliente=self.cliente_frecuente,
                segmento=SegmentoCliente.NUEVO,
                monto_total_gastado=Decimal('50.00'),
            ).exists()
        )
        self.assertFalse(
            SegmentoCliente.objects.filter(tienda=self.tienda, cliente=self.cliente_alto_valor).exists()
        )

    def test_listado_y_recalculo_no_exponen_datos_de_otra_tienda(self):
        self.crear_pedido(self.cliente_frecuente)
        self.crear_pedido(self.otro_cliente, tienda=self.otra_tienda, total='9000.00')
        recalcular_segmentos_tienda(self.tienda)
        recalcular_segmentos_tienda(self.otra_tienda)

        response = self.client.get(
            f'/api/tiendas/{self.tienda.pk}/clientes/segmentacion/'
        )

        self.assertEqual(response.status_code, 200)
        clientes = response.data['clientes']
        self.assertEqual([item['cliente']['email'] for item in clientes], ['frecuente@example.com'])
        self.assertFalse(
            SegmentoCliente.objects.filter(tienda=self.tienda, cliente=self.otro_cliente).exists()
        )

    def test_tienda_ajena_responde_not_found(self):
        response = self.client.get(
            f'/api/tiendas/{self.otra_tienda.pk}/clientes/segmentacion/'
        )
        self.assertEqual(response.status_code, 404)

    def test_bloquea_cliente_y_usuario_no_autenticado(self):
        self.client.force_authenticate(self.cliente_frecuente)
        forbidden = self.client.get(
            f'/api/tiendas/{self.tienda.pk}/clientes/segmentacion/'
        )
        self.assertEqual(forbidden.status_code, 403)

        self.client.force_authenticate(user=None)
        unauthorized = self.client.get(
            f'/api/tiendas/{self.tienda.pk}/clientes/segmentacion/'
        )
        self.assertEqual(unauthorized.status_code, 401)

    def test_reglas_validan_valores_mayores_a_cero(self):
        response = self.client.patch(
            f'/api/tiendas/{self.tienda.pk}/clientes/segmentacion/reglas/',
            {'dias_inactividad': 0},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ReglaSegmentacion.objects.filter(tienda=self.tienda).exists())

    def test_campana_solo_envia_a_clientes_del_segmento_en_esa_tienda(self):
        SegmentoCliente.objects.create(
            tienda=self.tienda,
            cliente=self.cliente_frecuente,
            segmento=SegmentoCliente.FRECUENTE,
            total_compras=3,
        )
        SegmentoCliente.objects.create(
            tienda=self.tienda,
            cliente=self.cliente_alto_valor,
            segmento=SegmentoCliente.ALTO_VALOR,
            total_compras=1,
        )
        SegmentoCliente.objects.create(
            tienda=self.otra_tienda,
            cliente=self.otro_cliente,
            segmento=SegmentoCliente.FRECUENTE,
            total_compras=3,
        )

        response = self.client.post(
            f'/api/tiendas/{self.tienda.pk}/crm/campanas-segmento/',
            {
                'segmento': SegmentoCliente.FRECUENTE,
                'nombre': 'Beneficio frecuente',
                'mensaje': 'Gracias por comprar en nuestra tienda.',
                'descuento_porcentaje': '10.00',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['destinatarios'], 1)
        notificaciones = NotificacionEnviada.objects.filter(campana_id=response.data['campana_id'])
        self.assertEqual(notificaciones.count(), 1)
        self.assertEqual(notificaciones.get().cliente_id, self.cliente_frecuente.pk)
        self.assertEqual(notificaciones.get().estado_entrega, 'enviado')
