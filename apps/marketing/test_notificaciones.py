from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase
from apps.usuarios.models import Rol, Usuario
from apps.tiendas.models import Tienda
from apps.catalogo.models import Producto, Variante
from apps.pedidos.models import Pedido, ItemPedido, Carrito, ItemCarrito
from apps.crm.models import Segmento, FichaCliente, CampanaCarrito
from .models import Cupon, DispositivoPush, NotificacionEnviada
from .notificaciones import crear_notificacion, entregar_notificacion, notificar_cupon


class NotificacionesTests(APITestCase):
    def setUp(self):
        empresa = Rol.objects.get_or_create(nombre='empresa')[0]
        cliente = Rol.objects.get_or_create(nombre='cliente')[0]
        self.empresa = Usuario.objects.create_user(email='empresa28@example.test', password='prueba', rol=empresa)
        self.cliente = Usuario.objects.create_user(email='cliente28@example.test', password='prueba', rol=cliente)
        self.otro = Usuario.objects.create_user(email='otro28@example.test', password='prueba', rol=cliente)
        self.tienda = Tienda.objects.create(propietario=self.empresa, nombre='Recordatorios')
        self.producto = Producto.objects.create(tienda=self.tienda, nombre='Café', slug='cafe28')
        self.variante = Variante.objects.create(producto=self.producto, sku='CU28-TEST', precio=Decimal('20'), stock=100)
        self.client.force_authenticate(self.cliente)

    def aviso(self, clave='evento', cliente=None):
        return crear_notificacion(tienda=self.tienda, cliente=cliente or self.cliente, titulo='Prueba',
            mensaje='Aviso', tipo='recompra', datos={'producto_id': self.producto.pk}, clave=clave)[0]

    def compra(self, dias, estado='entregado'):
        p = Pedido.objects.create(cliente=self.cliente, tienda=self.tienda, subtotal=20, total=20, estado_actual=estado)
        ItemPedido.objects.create(pedido=p, tienda=self.tienda, variante=self.variante, cantidad=1, precio_unitario=20)
        Pedido.objects.filter(pk=p.pk).update(fecha=timezone.now()-timedelta(days=dias))
        return p

    def command(self, nombre, **kwargs):
        call_command(nombre, stdout=StringIO(), **kwargs)

    def test_bandeja_aislada_marca_lectura_y_no_expone_tokens(self):
        propio = self.aviso()
        ajeno = self.aviso('ajeno', self.otro)
        r = self.client.get('/api/marketing/notificaciones/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual([n['id'] for n in r.data['notificaciones']], [propio.pk])
        self.assertNotIn('token', str(r.data))
        self.assertEqual(self.client.patch(f'/api/marketing/notificaciones/{ajeno.pk}/', {}).status_code, 404)
        self.assertEqual(self.client.patch(f'/api/marketing/notificaciones/{propio.pk}/', {}).status_code, 200)
        self.assertEqual(self.client.get('/api/marketing/notificaciones/').data['no_leidas'], 0)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/marketing/notificaciones/').status_code, 401)

    def test_paginacion_no_pierde_avisos_anteriores(self):
        for n in range(53): self.aviso(f'pagina:{n}')
        primero = self.client.get('/api/marketing/notificaciones/').data
        segundo = self.client.get(f"/api/marketing/notificaciones/?antes={primero['siguiente']}").data
        self.assertEqual(len(primero['notificaciones']), 50)
        self.assertEqual(len(segundo['notificaciones']), 3)
        self.assertEqual(self.client.get('/api/marketing/notificaciones/?antes=no').status_code, 400)

    def test_registro_dispositivo_reasigna_al_iniciar_y_solo_dueno_desactiva(self):
        data = {'token': 'token-ficticio-cu28-no-real', 'plataforma': 'android'}
        path = '/api/usuarios/dispositivos/'
        r = self.client.post(path, data, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(data['token'], str(r.data))
        self.assertFalse(r.data['push_disponible'])
        self.client.force_authenticate(self.otro)
        self.client.post(path, {**data, 'activo': False}, format='json')
        self.assertTrue(DispositivoPush.objects.get().activo)
        self.client.post(path, data, format='json')
        self.assertEqual(DispositivoPush.objects.get().usuario, self.otro)
        self.client.post(path, {**data, 'activo': False}, format='json')
        self.assertFalse(DispositivoPush.objects.get().activo)
        self.assertEqual(self.client.post(path, {**data, 'token': 'corto'}, format='json').status_code, 400)
        self.client.force_authenticate(self.empresa)
        self.assertEqual(self.client.post(path, data, format='json').status_code, 403)

    def test_idempotencia_y_bandeja_sin_firebase(self):
        with self.captureOnCommitCallbacks(execute=True):
            n = self.aviso()
            self.aviso()
        n.refresh_from_db()
        self.assertEqual(NotificacionEnviada.objects.count(), 1)
        self.assertEqual(n.estado_entrega, 'solo_bandeja')

    @override_settings(FCM_ENABLED=True)
    def test_envio_push_con_sdk_simulado_sin_consumir_servicio_real(self):
        dispositivo = DispositivoPush.objects.create(usuario=self.cliente, token='token-ficticio-no-real', plataforma='android')
        n = self.aviso()
        with patch('apps.marketing.notificaciones._firebase_app', return_value=object()), patch('firebase_admin.messaging.send', return_value='id-simulado') as send:
            entregar_notificacion(n.pk)
            entregar_notificacion(n.pk)
            self.assertEqual(send.call_count, 1)
            self.assertEqual(send.call_args.args[0].data['cliente_id'], str(self.cliente.pk))
            self.assertEqual(send.call_args.args[0].token, dispositivo.token)
        n.refresh_from_db()
        self.assertEqual(n.estado_entrega, 'enviado')

    @override_settings(FCM_ENABLED=True)
    def test_token_no_registrado_se_desactiva_y_no_marca_exito(self):
        from firebase_admin.messaging import UnregisteredError
        d = DispositivoPush.objects.create(usuario=self.cliente, token='token-ficticio-no-real', plataforma='android')
        n = self.aviso()
        with patch('apps.marketing.notificaciones._firebase_app', return_value=object()), patch('firebase_admin.messaging.send', side_effect=UnregisteredError('prueba')):
            entregar_notificacion(n.pk)
        d.refresh_from_db(); n.refresh_from_db()
        self.assertFalse(d.activo)
        self.assertEqual(n.estado_entrega, 'fallido')

    def test_recompra_solo_vencidas_no_repite_y_dryrun_no_escribe(self):
        self.compra(40)
        self.command('procesar_recordatorios_recompra', dry_run=True)
        self.assertEqual(NotificacionEnviada.objects.count(), 0)
        self.command('procesar_recordatorios_recompra')
        self.command('procesar_recordatorios_recompra')
        self.assertEqual(NotificacionEnviada.objects.count(), 1)
        self.assertEqual(NotificacionEnviada.objects.get().datos['producto_id'], str(self.producto.pk))

    def test_recompra_omite_pendientes_compra_reciente_sin_stock_inactivos(self):
        self.compra(40)
        nuevo = self.compra(1, 'pendiente')
        self.command('procesar_recordatorios_recompra')
        self.assertEqual(NotificacionEnviada.objects.count(), 0)
        Pedido.objects.filter(pk=nuevo.pk).update(estado_actual='cancelado')
        Variante.objects.filter(pk=self.variante.pk).update(stock=0)
        self.command('procesar_recordatorios_recompra')
        self.assertEqual(NotificacionEnviada.objects.count(), 0)

    def test_intervalo_recurrente_usa_historial_real(self):
        self.compra(40)
        self.compra(28)
        self.compra(16)
        self.command('procesar_recordatorios_recompra')
        self.assertEqual(NotificacionEnviada.objects.count(), 1)

    def test_cupon_segmentado_notifica_solo_destinatario_una_vez(self):
        segmento = Segmento.objects.create(tienda=self.tienda, nombre='VIP', criterio='Prueba')
        FichaCliente.objects.create(tienda=self.tienda, cliente=self.cliente, segmento=segmento)
        FichaCliente.objects.create(tienda=self.tienda, cliente=self.otro)
        c = Cupon.objects.create(tienda=self.tienda, codigo='VIP28', tipo_descuento='porcentaje', valor_descuento=10,
            fecha_expiracion=timezone.localdate()+timedelta(days=5), segmento_objetivo=segmento, usos_maximos=10)
        self.assertEqual(notificar_cupon(c), 1)
        self.assertEqual(notificar_cupon(c), 0)
        self.assertEqual(NotificacionEnviada.objects.get().cliente, self.cliente)

    def test_carrito_push_usa_actividad_y_no_repite_mismo_ciclo(self):
        CampanaCarrito.objects.create(tienda=self.tienda, activo=True, horas_inactividad=2)
        c = Carrito.objects.create(cliente=self.cliente, tienda=self.tienda)
        ItemCarrito.objects.create(carrito=c, tienda=self.tienda, variante=self.variante)
        self.command('notificar_carritos_push')
        self.assertFalse(NotificacionEnviada.objects.exists())
        Carrito.objects.filter(pk=c.pk).update(ultima_actividad=timezone.now()-timedelta(hours=3))
        self.command('notificar_carritos_push', dry_run=True)
        self.assertFalse(NotificacionEnviada.objects.exists())
        self.command('notificar_carritos_push'); self.command('notificar_carritos_push')
        self.assertEqual(NotificacionEnviada.objects.count(), 1)

    def test_jwt_login_refresh_logout_sigue_funcionando_con_sdk(self):
        self.client.force_authenticate(None)
        r = self.client.post('/api/auth/login/', {'email': self.cliente.email, 'password': 'prueba'}, format='json')
        self.assertEqual(r.status_code, 200)
        access, refresh = r.data['access'], r.data['refresh']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        self.assertEqual(self.client.get('/api/auth/perfil/').status_code, 200)
        r = self.client.post('/api/auth/token/refresh/', {'refresh': refresh}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.post('/api/auth/logout/', {'refresh': r.data.get('refresh', refresh)}, format='json').status_code, 200)


    def test_ventana_cooldown_y_estado_entregado(self):
        p = self.compra(90)
        self.command('procesar_recordatorios_recompra')
        self.assertFalse(NotificacionEnviada.objects.exists())
        Pedido.objects.filter(pk=p.pk).update(fecha=timezone.now()-timedelta(days=25), estado_actual='completado')
        self.command('procesar_recordatorios_recompra')
        self.assertFalse(NotificacionEnviada.objects.exists())
        Pedido.objects.filter(pk=p.pk).update(estado_actual='entregado')
        self.aviso('recordatorio-previo')
        self.command('procesar_recordatorios_recompra')
        self.assertEqual(NotificacionEnviada.objects.count(), 1)
        NotificacionEnviada.objects.update(fecha=timezone.now()-timedelta(days=8))
        self.command('procesar_recordatorios_recompra')
        self.assertEqual(NotificacionEnviada.objects.count(), 2)

    def test_campana_push_recuperacion_no_inventa_correos(self):
        from apps.crm.models import RegistroRecuperacionCarrito
        CampanaCarrito.objects.create(tienda=self.tienda, activo=True, horas_inactividad=2)
        c = Carrito.objects.create(cliente=self.cliente, tienda=self.tienda)
        ItemCarrito.objects.create(carrito=c, tienda=self.tienda, variante=self.variante)
        Carrito.objects.filter(pk=c.pk).update(ultima_actividad=timezone.now()-timedelta(hours=3))
        self.command('notificar_carritos_push')
        registro = RegistroRecuperacionCarrito.objects.get()
        self.assertFalse(registro.correo_enviado)
        respuesta = self.client.post('/api/pedidos/carrito/checkout/', {'metodo_pago': 'efectivo'}, format='json')
        self.assertEqual(respuesta.status_code, 201)
        registro.refresh_from_db()
        self.assertTrue(registro.recuperado)


    @override_settings(FCM_ENABLED=True)
    def test_firebase_sin_credenciales_preserva_bandeja_y_no_afirma_envio(self):
        DispositivoPush.objects.create(usuario=self.cliente, token='token-ficticio-no-real', plataforma='android')
        n = self.aviso()
        with patch('apps.marketing.notificaciones._firebase_app', side_effect=ValueError('configuracion ausente')):
            entregar_notificacion(n.pk)
        n.refresh_from_db()
        self.assertEqual(n.estado_entrega, 'sin_configuracion')
        self.assertEqual(self.client.get('/api/marketing/notificaciones/').status_code, 200)

    def test_tarea_periodica_dryrun_y_cupon_programado(self):
        FichaCliente.objects.create(tienda=self.tienda, cliente=self.cliente)
        c = Cupon.objects.create(tienda=self.tienda, codigo='FUTURO28', tipo_descuento='porcentaje', valor_descuento=10,
            fecha_inicio=timezone.localdate()+timedelta(days=1), fecha_expiracion=timezone.localdate()+timedelta(days=5), usos_maximos=10)
        self.command('procesar_marketing', dry_run=True)
        self.assertFalse(NotificacionEnviada.objects.exists())
        self.command('procesar_promociones')
        self.assertFalse(NotificacionEnviada.objects.exists())
        Cupon.objects.filter(pk=c.pk).update(fecha_inicio=timezone.localdate())
        self.command('procesar_promociones', dry_run=True)
        self.assertFalse(NotificacionEnviada.objects.exists())
        self.command('procesar_promociones'); self.command('procesar_promociones')
        self.assertEqual(NotificacionEnviada.objects.count(), 1)
