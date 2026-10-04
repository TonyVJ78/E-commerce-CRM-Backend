"""Pruebas del chatbot de recomendaciones.

La API de Claude se simula con `mock`: no se hace ninguna llamada de red.
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import anthropic
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.catalogo.models import Categoria, Producto, Variante
from apps.tiendas.models import Tienda
from apps.usuarios.models import Rol, Usuario

from .catalogo_busqueda import (
    buscar_productos, normalizar, productos_por_ids, resumen_para_modelo, terminos_de,
)
from .chatbot import _separar_sugerencias


URL = '/api/ia/chatbot/'


def texto(contenido):
    return SimpleNamespace(type='text', text=contenido)


def uso_herramienta(nombre, entrada, id_='toolu_1'):
    return SimpleNamespace(type='tool_use', name=nombre, input=entrada, id=id_)


def respuesta(*bloques, stop_reason='end_turn'):
    return SimpleNamespace(content=list(bloques), stop_reason=stop_reason)


class BaseCatalogo(APITestCase):
    @classmethod
    def setUpTestData(cls):
        rol_cliente = Rol.objects.get_or_create(nombre='cliente')[0]
        rol_empresa = Rol.objects.get_or_create(nombre='empresa')[0]
        cls.cliente = Usuario.objects.create_user(
            email='cliente-chat@example.com', password='Password123!', rol=rol_cliente)
        empresa = Usuario.objects.create_user(
            email='empresa-chat@example.com', password='Password123!', rol=rol_empresa)

        cls.tienda = Tienda.objects.create(propietario=empresa, nombre='Alpaca Andina')
        cls.tienda_cerrada = Tienda.objects.create(
            propietario=empresa, nombre='Tienda Cerrada', activa=False)
        textiles = Categoria.objects.create(tienda=cls.tienda, nombre='Textiles')
        cafe = Categoria.objects.create(tienda=cls.tienda, nombre='Caf├®')

        cls.chompa = cls._producto(
            'Chompa de Alpaca', textiles, Decimal('350.00'), stock=4,
            descripcion='Tejida a mano', etiquetas=['abrigo'])
        cls.chalina = cls._producto(
            'Chalina andina', textiles, Decimal('120.00'), stock=10,
            descripcion='Fibra de alpaca beb├®', oferta=Decimal('99.00'))
        cls.cafe = cls._producto(
            'Caf├® de los Yungas', cafe, Decimal('65.00'), stock=20, descripcion='Tostado medio')
        cls.agotado = cls._producto(
            'Gorro de alpaca', textiles, Decimal('80.00'), stock=0)
        cls.inactivo = cls._producto(
            'Poncho de alpaca', textiles, Decimal('500.00'), stock=3, activo=False)
        cls.de_tienda_cerrada = Producto.objects.create(
            tienda=cls.tienda_cerrada, nombre='Manta de alpaca', slug='manta')
        Variante.objects.create(
            producto=cls.de_tienda_cerrada, sku='M-1', precio=Decimal('200.00'), stock=5)

    @classmethod
    def _producto(cls, nombre, categoria, precio, stock, descripcion='', etiquetas=None,
                  oferta=None, activo=True):
        producto = Producto.objects.create(
            tienda=cls.tienda, categoria=categoria, nombre=nombre, slug=normalizar(nombre),
            descripcion=descripcion, etiquetas=etiquetas or [], activo=activo)
        Variante.objects.create(
            producto=producto, sku=f'SKU-{producto.id}', precio=precio,
            precio_oferta=oferta, stock=stock)
        return producto


class BusquedaCatalogoTests(BaseCatalogo):
    def test_ignora_tildes_plurales_y_palabras_vacias(self):
        self.assertEqual(terminos_de('Quiero unas chompas de ALPACA'), ['chompa', 'alpaca'])
        _, productos = buscar_productos('cafe yungas')
        self.assertEqual([p.id for p in productos], [self.cafe.id])

    def test_el_nombre_pesa_mas_que_la_descripcion(self):
        _, productos = buscar_productos('alpaca')
        # La chompa la nombra; la chalina solo en la descripci├│n.
        self.assertEqual([p.id for p in productos][:2], [self.chompa.id, self.chalina.id])

    def test_excluye_agotados_inactivos_y_tiendas_cerradas(self):
        _, productos = buscar_productos('alpaca')
        ids = {p.id for p in productos}
        self.assertNotIn(self.agotado.id, ids)
        self.assertNotIn(self.inactivo.id, ids)
        self.assertNotIn(self.de_tienda_cerrada.id, ids)

        _, con_agotados = buscar_productos('alpaca', solo_disponibles=False)
        self.assertIn(self.agotado.id, {p.id for p in con_agotados})

    def test_filtra_por_precio_efectivo_con_oferta(self):
        # La chalina cuesta 120 pero est├í en oferta a 99.
        _, productos = buscar_productos(categoria='textil', precio_max=100)
        self.assertEqual([p.id for p in productos], [self.chalina.id])

    def test_resumen_marca_la_oferta_de_la_variante_mas_barata(self):
        # Otra variante sin oferta, m├ís barata de lista que la oferta (120 ÔåÆ 99).
        Variante.objects.create(producto=self.chalina, sku='CH-2', precio=Decimal('110.00'), stock=1)
        datos = resumen_para_modelo(productos_por_ids([self.chalina.id])[0])
        self.assertEqual(datos['precio_bs'], '99.00')
        self.assertEqual(datos['precio_antes_bs'], '120.00')

        sin_oferta = resumen_para_modelo(productos_por_ids([self.cafe.id])[0])
        self.assertNotIn('precio_antes_bs', sin_oferta)

    def test_ignora_precios_invalidos(self):
        total, _ = buscar_productos(precio_max='barato')
        self.assertEqual(total, 3)  # chompa, chalina y caf├®: los visibles con stock

    def test_ordena_por_precio(self):
        _, productos = buscar_productos(orden='precio_asc')
        precios = [p.precio_min for p in productos]
        self.assertEqual(precios, sorted(precios))


@override_settings(ANTHROPIC_API_KEY='sk-ant-test', CHATBOT_MODEL='claude-haiku-4-5')
class ChatbotApiTests(BaseCatalogo):
    def setUp(self):
        cache.clear()  # el throttle guarda sus contadores en la cach├®
        self.client.force_authenticate(self.cliente)
        parche = mock.patch('apps.ia.chatbot.anthropic.Anthropic')
        self.Anthropic = parche.start()
        self.addCleanup(parche.stop)
        self.crear = self.Anthropic.return_value.messages.create

    def _enviar(self, *contenidos):
        mensajes = []
        for i, contenido in enumerate(contenidos):
            mensajes.append({'rol': 'usuario' if i % 2 == 0 else 'asistente', 'contenido': contenido})
        return self.client.post(URL, {'mensajes': mensajes}, format='json')

    def test_pregunta_para_acotar_sin_buscar(self):
        self.crear.return_value = respuesta(texto(
            '┬íClaro! ┬┐Para qui├®n es el regalo?\n\nSUGERENCIAS: Para mi mam├í | Para un amigo | Para m├¡'))

        res = self._enviar('quiero un regalo')

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['mensaje'], '┬íClaro! ┬┐Para qui├®n es el regalo?')
        self.assertEqual(res.data['sugerencias'], ['Para mi mam├í', 'Para un amigo', 'Para m├¡'])
        self.assertEqual(res.data['productos'], [])
        llamada = self.crear.call_args.kwargs
        self.assertEqual(llamada['model'], 'claude-haiku-4-5')
        self.assertIn('Textiles', llamada['system'])
        self.assertIn('Alpaca Andina', llamada['system'])
        self.assertNotIn('Tienda Cerrada', llamada['system'])

    def test_busca_y_devuelve_productos_citados(self):
        self.crear.side_effect = [
            respuesta(
                uso_herramienta('buscar_productos', {'consulta': 'alpaca', 'precio_max': 400}),
                stop_reason='tool_use'),
            respuesta(texto(
                f'Te recomiendo:\n- [Chompa de Alpaca](producto:{self.chompa.id}) ÔÇö **Bs 350.00**\n'
                f'- [Chalina andina](producto:{self.chalina.id})\n'
                f'- [Inventado](producto:999999)\n'
                f'- [Poncho](producto:{self.inactivo.id})\n'
                'SUGERENCIAS: Ver m├ís baratos | Otras tallas')),
        ]

        res = self._enviar('una chompa de alpaca de hasta 400 Bs')

        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            [p['id'] for p in res.data['productos']], [self.chompa.id, self.chalina.id])
        self.assertIn(f'(producto:{self.chompa.id})', res.data['mensaje'])
        # Los ids inventados o que ya no est├ín a la venta pierden el enlace.
        self.assertIn('- Inventado', res.data['mensaje'])
        self.assertIn('- Poncho', res.data['mensaje'])
        self.assertNotIn('SUGERENCIAS', res.data['mensaje'])

        # El resultado de la herramienta vuelve al modelo con los productos reales.
        segunda = self.crear.call_args_list[1].kwargs['messages']
        resultado = segunda[-1]['content'][0]
        self.assertEqual(resultado['type'], 'tool_result')
        self.assertEqual(resultado['tool_use_id'], 'toolu_1')
        self.assertIn('Chompa de Alpaca', resultado['content'])
        self.assertNotIn('Poncho', resultado['content'])

    def test_ver_producto_con_id_inexistente_es_error_de_herramienta(self):
        self.crear.side_effect = [
            respuesta(uso_herramienta('ver_producto', {'producto_id': 999999}), stop_reason='tool_use'),
            respuesta(texto('No encontr├® ese producto.')),
        ]
        res = self._enviar('detalle del 999999')
        self.assertEqual(res.status_code, 200)
        resultado = self.crear.call_args_list[1].kwargs['messages'][-1]['content'][0]
        self.assertTrue(resultado['is_error'])

    def test_limita_las_vueltas_de_herramientas(self):
        busqueda = respuesta(uso_herramienta('buscar_productos', {'consulta': 'x'}), stop_reason='tool_use')
        self.crear.side_effect = [busqueda] * 4 + [respuesta(texto('Esto encontr├®.'))]

        res = self._enviar('algo')

        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.crear.call_count, 5)
        self.assertEqual(self.crear.call_args.kwargs['tool_choice'], {'type': 'none'})

    def test_historial_descarta_saludo_y_junta_roles_repetidos(self):
        self.crear.return_value = respuesta(texto('Ok'))
        res = self.client.post(URL, {'mensajes': [
            {'rol': 'asistente', 'contenido': '┬íHola! Soy Kantu.'},
            {'rol': 'usuario', 'contenido': 'hola'},
            {'rol': 'usuario', 'contenido': 'busco caf├®'},
        ]}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            self.crear.call_args.kwargs['messages'],
            [{'role': 'user', 'content': 'hola\n\nbusco caf├®'}])

    def test_valida_el_historial(self):
        res = self.client.post(URL, {'mensajes': [
            {'rol': 'usuario', 'contenido': 'hola'},
            {'rol': 'asistente', 'contenido': 'Hola'},
        ]}, format='json')
        self.assertEqual(res.status_code, 400)
        res = self.client.post(URL, {'mensajes': []}, format='json')
        self.assertEqual(res.status_code, 400)
        self.crear.assert_not_called()

    def test_requiere_autenticacion(self):
        self.client.force_authenticate(None)
        self.assertEqual(self._enviar('hola').status_code, 401)

    @override_settings(ANTHROPIC_API_KEY='')
    def test_sin_clave_responde_503(self):
        self.assertEqual(self._enviar('hola').status_code, 503)

    def test_error_de_la_api_responde_502(self):
        self.crear.side_effect = anthropic.APIConnectionError(request=mock.Mock())
        self.assertEqual(self._enviar('hola').status_code, 502)


class FichaProductoTests(BaseCatalogo):
    """GET /api/catalogo/productos/<id>/, destino de las tarjetas del chatbot."""

    def test_es_publica_y_trae_variantes(self):
        res = self.client.get(f'/api/catalogo/productos/{self.chompa.id}/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['nombre'], 'Chompa de Alpaca')
        self.assertEqual(len(res.data['variantes']), 1)

    def test_no_muestra_productos_retirados(self):
        for producto in (self.inactivo, self.de_tienda_cerrada):
            res = self.client.get(f'/api/catalogo/productos/{producto.id}/')
            self.assertEqual(res.status_code, 404)


class SugerenciasTests(APITestCase):
    def test_separa_la_ultima_linea_de_sugerencias(self):
        mensaje, sugerencias = _separar_sugerencias(
            'Hola\nSUGERENCIAS: A | "B" | A | ' + 'x' * 50)
        self.assertEqual(mensaje, 'Hola')
        self.assertEqual(sugerencias, ['A', 'B'])

    def test_sin_sugerencias(self):
        self.assertEqual(_separar_sugerencias('Solo texto'), ('Solo texto', []))
