"""Pruebas del panel de satisfacción de clientes (reseñas de la tienda)."""

import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import anthropic
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.catalogo.models import Producto, Variante
from apps.tiendas.models import Tienda
from apps.usuarios.models import Rol, Usuario

from . import satisfaccion_ia
from .models import ItemPedido, Pedido, Resena

RESUMEN_VALIDO = {
    'resumen': 'Clientes contentos con la calidad, quejas por el envío.',
    'temas_positivos': ['Buena calidad'],
    'temas_negativos': ['Envío lento'],
    'recomendacion': 'Mejorar los tiempos de envío.',
}


def fecha(texto):
    return timezone.make_aware(datetime.strptime(texto, '%Y-%m-%d %H:%M'))


class BaseSatisfaccion(APITestCase):
    def setUp(self):
        cache.clear()
        rol_cliente = Rol.objects.get_or_create(nombre='cliente')[0]
        rol_empresa = Rol.objects.get_or_create(nombre='empresa')[0]
        self.empresa = Usuario.objects.create_user(
            email='sat-empresa@example.com', password='Password123!', rol=rol_empresa)
        self.otra_empresa = Usuario.objects.create_user(
            email='sat-otra@example.com', password='Password123!', rol=rol_empresa)
        self.clientes = [
            Usuario.objects.create_user(
                email=f'sat-cliente{i}@example.com', password='Password123!',
                rol=rol_cliente, first_name=f'Cliente{i}')
            for i in range(4)
        ]
        self.tienda = Tienda.objects.create(
            propietario=self.empresa, nombre='Tienda Sat', slug='tienda-sat')
        self.tienda_ajena = Tienda.objects.create(
            propietario=self.otra_empresa, nombre='Tienda Ajena', slug='tienda-ajena')
        self.camisa = self.producto(self.tienda, 'Camisa', 'camisa-sat')
        self.gorra = self.producto(self.tienda, 'Gorra', 'gorra-sat')

    def producto(self, tienda, nombre, slug):
        producto = Producto.objects.create(tienda=tienda, nombre=nombre, slug=slug)
        Variante.objects.create(
            producto=producto, nombre='Unica', sku=f'SKU-{slug}', precio=Decimal('10'), stock=100)
        return producto

    def resena(self, cliente, calificacion, producto=None, comentario='', cuando=None, tienda=None):
        resena = Resena.objects.create(
            tienda=tienda or self.tienda, cliente=cliente, producto=producto,
            calificacion=calificacion, comentario=comentario)
        if cuando:
            Resena.objects.filter(pk=resena.pk).update(fecha=cuando)
        return resena

    def pedido(self, cliente, estado='entregado', producto=None, cuando=None):
        pedido = Pedido.objects.create(
            cliente=cliente, tienda=self.tienda, estado_actual=estado,
            subtotal=Decimal('10'), total=Decimal('10'))
        if producto:
            ItemPedido.objects.create(
                tienda=self.tienda, pedido=pedido, variante=producto.variantes.get(),
                cantidad=1, precio_unitario=Decimal('10'))
        Pedido.objects.filter(pk=pedido.pk).update(estado_actual=estado)
        if cuando:
            Pedido.objects.filter(pk=pedido.pk).update(fecha=cuando)
        return pedido

    def url(self, tienda=None, sufijo=''):
        return f'/api/tiendas/{(tienda or self.tienda).id}/satisfaccion/{sufijo}'


class MetricasSatisfaccionTests(BaseSatisfaccion):
    def test_promedio_distribucion_y_sentimiento(self):
        c0, c1, c2, c3 = self.clientes
        self.resena(c0, 5)
        self.resena(c1, 4)
        self.resena(c2, 3)
        self.resena(c3, 1)
        self.client.force_authenticate(self.empresa)

        r = self.client.get(self.url())

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['total'], 4)
        self.assertEqual(r.data['promedio'], 3.25)
        por_estrella = {d['estrellas']: d for d in r.data['distribucion']}
        self.assertEqual([por_estrella[e]['cantidad'] for e in range(1, 6)], [1, 0, 1, 1, 1])
        self.assertEqual(por_estrella[5]['porcentaje'], 25.0)
        self.assertEqual(r.data['sentimiento']['positivas'], {'cantidad': 2, 'porcentaje': 50.0})
        self.assertEqual(r.data['sentimiento']['neutras'], {'cantidad': 1, 'porcentaje': 25.0})
        self.assertEqual(r.data['sentimiento']['negativas'], {'cantidad': 1, 'porcentaje': 25.0})

    def test_sin_resenas_devuelve_ceros(self):
        self.client.force_authenticate(self.empresa)
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['total'], 0)
        self.assertIsNone(r.data['promedio'])
        self.assertEqual(r.data['tendencia_mensual'], [])
        self.assertEqual(r.data['tasa_respuesta']['porcentaje'], 0.0)

    def test_tendencia_mensual(self):
        c0, c1, c2, _ = self.clientes
        self.resena(c0, 2, cuando=fecha('2026-09-10 12:00'))
        self.resena(c1, 4, cuando=fecha('2026-10-05 12:00'))
        self.resena(c2, 5, cuando=fecha('2026-10-20 12:00'))
        self.client.force_authenticate(self.empresa)

        r = self.client.get(self.url())

        self.assertEqual(r.data['tendencia_mensual'], [
            {'mes': '2026-09', 'promedio': 2.0, 'cantidad': 1},
            {'mes': '2026-10', 'promedio': 4.5, 'cantidad': 2},
        ])

    def test_ranking_de_productos_respeta_el_minimo(self):
        clientes = self.clientes
        for cliente in clientes[:3]:
            self.resena(cliente, 5, producto=self.camisa)
        for cliente in clientes[:3]:
            self.resena(cliente, 2, producto=self.gorra)
        otro = self.producto(self.tienda, 'Medias', 'medias-sat')
        self.resena(clientes[0], 1, producto=otro)
        self.client.force_authenticate(self.empresa)

        r = self.client.get(self.url())

        mejores = r.data['productos_mejor_calificados']
        peores = r.data['productos_peor_calificados']
        self.assertEqual([p['nombre'] for p in mejores], ['Camisa', 'Gorra'])
        self.assertEqual([p['nombre'] for p in peores], ['Gorra', 'Camisa'])
        self.assertEqual(mejores[0]['promedio'], 5.0)
        self.assertEqual(mejores[0]['cantidad'], 3)

        r = self.client.get(self.url(), {'min_resenas': 1})
        self.assertIn('Medias', [p['nombre'] for p in r.data['productos_peor_calificados']])

    def test_ultimas_resenas_solo_con_comentario_y_sin_email(self):
        c0, c1, _, _ = self.clientes
        self.resena(c0, 5, comentario='Excelente', cuando=fecha('2026-10-01 10:00'))
        self.resena(c1, 3, comentario='', cuando=fecha('2026-10-02 10:00'))
        self.resena(c1, 2, producto=self.camisa, comentario='Se despegó',
                    cuando=fecha('2026-10-03 10:00'))
        self.client.force_authenticate(self.empresa)

        r = self.client.get(self.url())

        ultimas = r.data['ultimas_resenas']
        self.assertEqual([u['comentario'] for u in ultimas], ['Se despegó', 'Excelente'])
        self.assertEqual(ultimas[0]['producto'], 'Camisa')
        self.assertIsNone(ultimas[1]['producto'])
        self.assertNotIn('@', json.dumps(ultimas))

    def test_tasa_de_respuesta(self):
        c0, c1, c2, c3 = self.clientes
        self.pedido(c0, producto=self.camisa)
        self.pedido(c1, producto=self.camisa)
        self.pedido(c2, producto=self.camisa)
        self.pedido(c3, estado='enviado', producto=self.camisa)
        self.resena(c0, 5, producto=self.camisa)
        self.resena(c1, 4)
        self.resena(c3, 4, producto=self.camisa)
        self.client.force_authenticate(self.empresa)

        r = self.client.get(self.url())

        self.assertEqual(r.data['tasa_respuesta'], {
            'pedidos_entregados': 3, 'pedidos_calificados': 2, 'porcentaje': 66.7,
        })

    def test_resena_de_otro_producto_no_califica_el_pedido(self):
        c0 = self.clientes[0]
        self.pedido(c0, producto=self.camisa)
        self.resena(c0, 5, producto=self.gorra)
        self.client.force_authenticate(self.empresa)

        r = self.client.get(self.url())

        self.assertEqual(r.data['tasa_respuesta']['pedidos_calificados'], 0)

    def test_rango_de_fechas(self):
        c0, c1, c2, _ = self.clientes
        self.resena(c0, 1, comentario='viejo', cuando=fecha('2026-08-31 23:00'))
        self.resena(c1, 5, comentario='dentro 1', cuando=fecha('2026-09-01 00:30'))
        self.resena(c2, 3, comentario='dentro 2', cuando=fecha('2026-09-30 23:30'))
        self.pedido(c0, cuando=fecha('2026-08-15 10:00'))
        self.pedido(c1, cuando=fecha('2026-09-15 10:00'))
        self.client.force_authenticate(self.empresa)

        r = self.client.get(self.url(), {'desde': '2026-09-01', 'hasta': '2026-09-30'})

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['total'], 2)
        self.assertEqual(r.data['promedio'], 4.0)
        self.assertEqual(r.data['tasa_respuesta']['pedidos_entregados'], 1)
        self.assertEqual(
            {u['comentario'] for u in r.data['ultimas_resenas']}, {'dentro 1', 'dentro 2'})

    def test_filtros_invalidos(self):
        self.client.force_authenticate(self.empresa)
        r = self.client.get(self.url(), {'desde': 'ayer'})
        self.assertEqual(r.status_code, 400)
        r = self.client.get(self.url(), {'desde': '2026-10-02', 'hasta': '2026-10-01'})
        self.assertEqual(r.status_code, 400)
        r = self.client.get(self.url(), {'min_resenas': 0})
        self.assertEqual(r.status_code, 400)


class AccesoSatisfaccionTests(BaseSatisfaccion):
    def test_empresa_no_ve_resenas_de_tienda_ajena(self):
        self.resena(self.clientes[0], 5, comentario='mía')
        self.resena(self.clientes[1], 1, comentario='ajena', tienda=self.tienda_ajena)
        self.client.force_authenticate(self.empresa)

        r = self.client.get(self.url())
        self.assertEqual(r.data['total'], 1)
        self.assertEqual([u['comentario'] for u in r.data['ultimas_resenas']], ['mía'])

        self.assertEqual(self.client.get(self.url(self.tienda_ajena)).status_code, 404)
        self.assertEqual(
            self.client.post(self.url(self.tienda_ajena, 'resumen-ia/'), {}, format='json').status_code,
            404,
        )

    def test_las_metricas_de_cada_tienda_son_independientes(self):
        self.resena(self.clientes[0], 5)
        self.resena(self.clientes[1], 2, tienda=self.tienda_ajena)
        self.client.force_authenticate(self.otra_empresa)

        r = self.client.get(self.url(self.tienda_ajena))

        self.assertEqual(r.data['total'], 1)
        self.assertEqual(r.data['promedio'], 2.0)

    def test_cliente_recibe_403(self):
        self.client.force_authenticate(self.clientes[0])
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.assertEqual(
            self.client.post(self.url(sufijo='resumen-ia/'), {}, format='json').status_code, 403)

    def test_sin_sesion_recibe_401(self):
        self.assertEqual(self.client.get(self.url()).status_code, 401)


def respuesta_claude(texto=None, stop_reason='end_turn'):
    contenido = [SimpleNamespace(type='thinking', text='pensando')]
    if texto is not None:
        contenido.append(SimpleNamespace(type='text', text=texto))
    return SimpleNamespace(stop_reason=stop_reason, content=contenido)


@override_settings(ANTHROPIC_API_KEY='clave-de-prueba', ANTHROPIC_MODEL='claude-haiku-5-5')
class ResumenIaSatisfaccionTests(BaseSatisfaccion):
    def setUp(self):
        super().setUp()
        self.resena(self.clientes[0], 5, comentario='Muy buena calidad')
        self.resena(self.clientes[1], 2, producto=self.camisa, comentario='El envío tardó mucho')
        self.resena(self.clientes[2], 4)
        self.client.force_authenticate(self.empresa)

    def resumir(self, **cuerpo):
        return self.client.post(self.url(sufijo='resumen-ia/'), cuerpo, format='json')

    def con_cliente(self, **config):
        parche = mock.patch('apps.pedidos.satisfaccion_ia.anthropic.Anthropic')
        constructor = parche.start()
        self.addCleanup(parche.stop)
        constructor.return_value.messages.create.return_value = config.pop(
            'respuesta', None) or respuesta_claude(json.dumps(RESUMEN_VALIDO))
        if 'error' in config:
            constructor.return_value.messages.create.side_effect = config['error']
        return constructor.return_value.messages.create

    def test_resumen_exitoso_llama_con_los_parametros_esperados(self):
        crear = self.con_cliente()

        r = self.resumir()

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['resumen'], RESUMEN_VALIDO['resumen'])
        self.assertEqual(r.data['temas_negativos'], ['Envío lento'])
        self.assertEqual(r.data['comentarios_analizados'], 2)
        kwargs = crear.call_args.kwargs
        self.assertEqual(kwargs['model'], 'claude-haiku-5-5')
        self.assertEqual(kwargs['output_config']['effort'], 'low')
        self.assertGreaterEqual(kwargs['max_tokens'], 2000)
        self.assertNotIn('temperature', kwargs)

    def test_no_envia_datos_personales_al_modelo(self):
        crear = self.con_cliente()

        self.resumir()

        enviado = json.dumps(crear.call_args.kwargs['messages'], ensure_ascii=False)
        self.assertIn('Muy buena calidad', enviado)
        self.assertIn('Camisa', enviado)
        self.assertNotIn('@', enviado)
        self.assertNotIn('Cliente0', enviado)

    def test_limita_la_cantidad_de_comentarios_enviados(self):
        crear = self.con_cliente()
        Resena.objects.bulk_create([
            Resena(tienda=self.tienda, cliente=self.clientes[3], calificacion=3, comentario=f'c{i}')
            for i in range(satisfaccion_ia.MAX_COMENTARIOS + 20)
        ])

        r = self.resumir()

        self.assertEqual(r.data['comentarios_analizados'], satisfaccion_ia.MAX_COMENTARIOS)
        enviado = crear.call_args.kwargs['messages'][0]['content']
        self.assertEqual(enviado.count('"calificacion"'), satisfaccion_ia.MAX_COMENTARIOS)

    def test_respeta_el_rango_de_fechas(self):
        self.resena(self.clientes[3], 1, comentario='de agosto', cuando=fecha('2026-08-10 10:00'))
        crear = self.con_cliente()

        r = self.resumir(desde='2026-08-01', hasta='2026-08-31')

        self.assertEqual(r.data['comentarios_analizados'], 1)
        enviado = crear.call_args.kwargs['messages'][0]['content']
        self.assertIn('de agosto', enviado)
        self.assertNotIn('Muy buena calidad', enviado)

    def test_sin_comentarios_no_llama_a_la_ia(self):
        crear = self.con_cliente()
        r = self.resumir(desde='2020-01-01', hasta='2020-01-31')
        self.assertEqual(r.status_code, 400)
        crear.assert_not_called()

    @override_settings(ANTHROPIC_API_KEY='')
    def test_sin_api_key_devuelve_503(self):
        crear = self.con_cliente()
        r = self.resumir()
        self.assertEqual(r.status_code, 503)
        crear.assert_not_called()

    def test_rechazo_del_modelo_devuelve_502(self):
        self.con_cliente(respuesta=respuesta_claude(stop_reason='refusal'))
        self.assertEqual(self.resumir().status_code, 502)

    def test_respuesta_cortada_por_max_tokens_devuelve_502(self):
        self.con_cliente(respuesta=respuesta_claude('{"resumen"', stop_reason='max_tokens'))
        self.assertEqual(self.resumir().status_code, 502)

    def test_respuesta_con_forma_invalida_devuelve_502(self):
        self.con_cliente(respuesta=respuesta_claude(json.dumps({'resumen': 'solo esto'})))
        self.assertEqual(self.resumir().status_code, 502)

    def test_texto_que_no_es_json_devuelve_502(self):
        self.con_cliente(respuesta=respuesta_claude('Aquí tienes el resumen'))
        self.assertEqual(self.resumir().status_code, 502)

    def test_error_de_la_api_devuelve_502(self):
        peticion = mock.Mock()
        self.con_cliente(error=anthropic.APIConnectionError(request=peticion))
        r = self.resumir()
        self.assertEqual(r.status_code, 502)
