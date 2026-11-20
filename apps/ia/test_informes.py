"""Pruebas de los informes de tienda con IA (CU-34).

La API de Claude se simula con `mock`: no se hace ninguna llamada de red. Los
pedidos se crean como en el checkout real: el trigger de la base recalcula el
total y descuenta el stock.
"""

from datetime import datetime
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from unittest import mock

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.test import APITestCase

from apps.catalogo.models import Categoria, Producto, Variante
from apps.crm.models import CampanaCarrito, RegistroRecuperacionCarrito
from apps.finanzas.models import GastoOperativo
from apps.marketing.models import Cupon, CuponUso
from apps.pedidos.models import Carrito, HistorialEstadoPedido, ItemPedido, Pedido, Resena
from apps.tiendas.models import Tienda, UsuarioTienda
from apps.usuarios.models import Permiso, Rol, RolPermiso, Usuario

from . import informes_consultas as consultas
from .informes_exportar import _formato, _lineas_markdown, generar_pdf, generar_xlsx
from .models import EventoUsuario, ReporteGenerado


URL_GENERAR = '/api/ia/informes/generar/'
URL_CONTEXTO = '/api/ia/informes/contexto/'
URL_LISTA = '/api/ia/informes/'


def texto(contenido):
    return SimpleNamespace(type='text', text=contenido)


def uso_herramienta(nombre, entrada, id_='toolu_1'):
    return SimpleNamespace(type='tool_use', name=nombre, input=entrada, id=id_)


def respuesta(*bloques, stop_reason='end_turn'):
    return SimpleNamespace(content=list(bloques), stop_reason=stop_reason)


def mensajes(*textos):
    return {'mensajes': [{'rol': 'usuario', 'contenido': t} for t in textos]}


class BaseInformes(APITestCase):
    @classmethod
    def setUpTestData(cls):
        rol_empresa = Rol.objects.get_or_create(nombre='empresa')[0]
        rol_admin = Rol.objects.get_or_create(nombre='administrador')[0]
        rol_cliente = Rol.objects.get_or_create(nombre='cliente')[0]

        cls.empresa = Usuario.objects.create_user(
            email='empresa-inf@example.com', password='Password123!', rol=rol_empresa)
        cls.otra_empresa = Usuario.objects.create_user(
            email='otra-inf@example.com', password='Password123!', rol=rol_empresa)
        cls.admin = Usuario.objects.create_user(
            email='admin-inf@example.com', password='Password123!', rol=rol_admin)
        cls.cliente = Usuario.objects.create_user(
            email='cliente-inf@example.com', password='Password123!', rol=rol_cliente)
        # Encargado: rol cliente (sin permiso de informes) asignado a una tienda.
        cls.encargado = Usuario.objects.create_user(
            email='encargado-inf@example.com', password='Password123!', rol=rol_cliente)

        cls.tienda = Tienda.objects.create(propietario=cls.empresa, nombre='Alpaca Andina')
        cls.tienda_ajena = Tienda.objects.create(propietario=cls.otra_empresa, nombre='Tienda Ajena')
        UsuarioTienda.objects.create(usuario=cls.encargado, tienda=cls.tienda, rol_interno='encargado')

        textiles = Categoria.objects.create(tienda=cls.tienda, nombre='Textiles')
        cls.chompa = cls._variante(cls.tienda, textiles, 'Chompa de Alpaca', Decimal('350.00'), stock=50)
        cls.gorro = cls._variante(cls.tienda, textiles, 'Gorro andino', Decimal('80.00'), stock=3,
                                  stock_minimo=5)
        cls.ajena = cls._variante(cls.tienda_ajena, None, 'Producto ajeno', Decimal('999.00'), stock=50)

        cls._pedido(cls.tienda, [(cls.chompa, 2), (cls.gorro, 1)])        # 780
        cls._pedido(cls.tienda, [(cls.chompa, 1)])                        # 350
        cls._pedido(cls.tienda, [(cls.gorro, 1)], estado='cancelado')     # no cuenta
        cls._pedido(cls.tienda_ajena, [(cls.ajena, 5)])                   # otra tienda

    @classmethod
    def _variante(cls, tienda, categoria, nombre, precio, stock, stock_minimo=5):
        producto = Producto.objects.create(tienda=tienda, categoria=categoria, nombre=nombre, slug=nombre.lower())
        return Variante.objects.create(producto=producto, sku=f'SKU-{producto.id}', precio=precio,
                                       stock=stock, stock_minimo=stock_minimo)

    @classmethod
    def _pedido(cls, tienda, lineas, estado='pendiente'):
        pedido = Pedido.objects.create(cliente=cls.cliente, tienda=tienda, subtotal=0, total=0,
                                       estado_actual='pendiente')
        for variante, cantidad in lineas:
            ItemPedido.objects.create(tienda=tienda, pedido=pedido, variante=variante,
                                      cantidad=cantidad, precio_unitario=variante.precio)
        if estado != 'pendiente':
            Pedido.objects.filter(pk=pedido.pk).update(estado_actual=estado)
        return pedido


class MotorConsultasTests(BaseInformes):
    def _ejecutar(self, spec, tiendas=None):
        tiendas = tiendas or [self.tienda.id]
        return consultas.ejecutar(consultas.normalizar(spec), tiendas)

    def test_ventas_por_producto_excluye_cancelados_y_otras_tiendas(self):
        r = self._ejecutar({'fuente': 'ventas_productos', 'agrupar_por': ['producto'],
                            'metricas': ['unidades', 'ingresos']})
        self.assertEqual([c['clave'] for c in r['columnas']], ['producto', 'unidades', 'ingresos'])
        self.assertEqual(r['filas'], [['Chompa de Alpaca', 3, 1050.0], ['Gorro andino', 1, 80.0]])

    def test_conteos_distintos_y_promedios_no_son_sumables(self):
        r = self._ejecutar({'fuente': 'ventas_productos', 'agrupar_por': ['producto'],
                            'metricas': ['unidades', 'pedidos', 'precio_promedio']})
        self.assertEqual([c['sumable'] for c in r['columnas']], [False, True, False, False])
        self.assertEqual(consultas.resumen_para_modelo(r)['totales_de_la_tabla'], {'unidades': 4})

    def test_totales_sin_agrupar(self):
        r = self._ejecutar({'fuente': 'pedidos', 'metricas': ['pedidos', 'monto_total', 'ticket_promedio']})
        self.assertEqual(r['filas'], [[2, 1130.0, 565.0]])

    def test_filtro_de_estado_incluye_cancelados(self):
        r = self._ejecutar({'fuente': 'pedidos', 'agrupar_por': ['estado'], 'metricas': ['pedidos'],
                            'filtros': {'estados': ['cancelado']}})
        self.assertEqual(r['filas'], [['Cancelado', 1]])

    def test_inventario_stock_bajo(self):
        r = self._ejecutar({'fuente': 'inventario', 'agrupar_por': ['producto'], 'metricas': ['stock'],
                            'filtros': {'solo_stock_bajo': True}})
        self.assertEqual([f[0] for f in r['filas']], ['Gorro andino'])

    def test_serie_por_mes_ordena_por_tiempo(self):
        r = self._ejecutar({'fuente': 'pedidos', 'agrupar_por': ['mes'], 'metricas': ['monto_total']})
        self.assertEqual(len(r['filas']), 1)
        self.assertRegex(r['filas'][0][0], r'^\d{4}-\d{2}$')

    def test_limite_marca_truncado(self):
        r = self._ejecutar({'fuente': 'ventas_productos', 'agrupar_por': ['producto'],
                            'metricas': ['unidades'], 'limite': 1})
        self.assertEqual(len(r['filas']), 1)
        self.assertTrue(r['truncado'])
        self.assertEqual(r['total_filas'], 2)

    def test_filtros_fuera_de_su_objeto_se_aplican(self):
        # El modelo a veces pone fecha_desde junto a `fuente`: debe filtrar igual.
        spec = consultas.normalizar({'fuente': 'pedidos', 'metricas': ['pedidos'], 'fecha_desde': '2999-01-01'})
        self.assertEqual(spec['filtros'], {'fecha_desde': '2999-01-01'})
        self.assertEqual(consultas.ejecutar(spec, [self.tienda.id])['filas'], [[0]])
        self.assertIn('Periodo: 2999-01-01', consultas.describir_filtros(spec, {}))

    def test_sin_fecha_el_periodo_es_todo_el_historial(self):
        spec = consultas.normalizar({'fuente': 'pedidos', 'metricas': ['pedidos']})
        self.assertIn('Periodo: todo el historial', consultas.describir_filtros(spec, {}))
        resumen = consultas.resumen_para_modelo(consultas.ejecutar(spec, [self.tienda.id]), spec)
        self.assertIn('todo el historial', resumen['filtros_aplicados'])

    def test_especificaciones_invalidas(self):
        casos = [
            {'fuente': 'usuarios', 'metricas': ['x']},
            {'fuente': 'pedidos', 'metricas': ['stock']},
            {'fuente': 'pedidos', 'agrupar_por': ['sku'], 'metricas': ['pedidos']},
            {'fuente': 'inventario', 'metricas': ['stock'], 'filtros': {'fecha_desde': '2026-01-01'}},
            {'fuente': 'pedidos', 'metricas': ['pedidos'], 'filtros': {'sql': 'drop table'}},
            {'fuente': 'pedidos', 'metricas': ['pedidos'], 'sql': 'drop table'},
            {'fuente': 'pedidos', 'metricas': ['pedidos'], 'filtros': {'fecha_desde': 'ayer'}},
        ]
        for spec in casos:
            with self.subTest(spec=spec), self.assertRaises(consultas.ConsultaInvalida):
                self._ejecutar(spec)

    def test_alcance_por_rol(self):
        self.assertEqual(set(consultas.tiendas_permitidas(self.empresa)), {self.tienda})
        self.assertEqual(set(consultas.tiendas_permitidas(self.encargado)), {self.tienda})
        self.assertEqual(set(consultas.tiendas_permitidas(self.admin)), {self.tienda, self.tienda_ajena})


class ClaudeSimulado:
    """Reemplaza al cliente de Anthropic: `self.crear` es `messages.create`."""

    def setUp(self):
        super().setUp()
        cache.clear()  # el throttle guarda sus contadores en la caché
        parche = mock.patch('apps.ia.informes.anthropic.Anthropic')
        self.Anthropic = parche.start()
        self.addCleanup(parche.stop)
        self.crear = self.Anthropic.return_value.messages.create

    def _consulta_y_presenta(self, spec, **presentar):
        self.crear.side_effect = [
            respuesta(uso_herramienta('consultar_datos', spec, 'toolu_1'), stop_reason='tool_use'),
            respuesta(uso_herramienta('presentar_informe', {
                'consulta_id': 1, 'titulo': 'Más vendidos', 'analisis': '- La **chompa** lidera.',
                'grafico': {'tipo': 'barras', 'etiqueta': 'producto', 'valor': 'unidades'},
                'sugerencias': ['Ventas por semana'], **presentar,
            }, 'toolu_2'), stop_reason='tool_use'),
        ]


@override_settings(ANTHROPIC_API_KEY='sk-ant-test', INFORMES_MODEL='claude-haiku-5-5')
class InformesApiTests(ClaudeSimulado, BaseInformes):
    def test_cliente_sin_permiso_recibe_403(self):
        self.client.force_authenticate(self.cliente)
        self.assertEqual(self.client.get(URL_CONTEXTO).status_code, 403)
        self.assertEqual(self.client.post(URL_GENERAR, mensajes('hola'), format='json').status_code, 403)

    def test_permiso_se_concede_desde_la_matriz(self):
        # El encargado tiene rol cliente: con el permiso asignado al rol ya puede.
        rol_cliente = Rol.objects.get(nombre='cliente')
        for codigo in ('informes.ver', 'informes.crear'):
            RolPermiso.objects.create(rol=rol_cliente, permiso=Permiso.objects.get(codigo=codigo))
        self.client.force_authenticate(self.encargado)
        res = self.client.get(URL_CONTEXTO)
        self.assertEqual(res.status_code, 200)
        self.assertEqual([t['id'] for t in res.data['tiendas']], [self.tienda.id])

    def test_contexto_de_empresa(self):
        self.client.force_authenticate(self.empresa)
        res = self.client.get(URL_CONTEXTO)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['tiendas'], [{'id': self.tienda.id, 'nombre': 'Alpaca Andina'}])
        self.assertTrue(res.data['puede_crear'])
        self.assertFalse(res.data['es_administrador'])

    def test_pedido_general_devuelve_preguntas(self):
        self.client.force_authenticate(self.empresa)
        self.crear.return_value = respuesta(texto(
            '¿Qué quieres medir y de qué periodo?\nSUGERENCIAS: Ventas del mes | Stock bajo'))
        res = self.client.post(URL_GENERAR, mensajes('quiero un informe'), format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['tipo'], 'pregunta')
        self.assertEqual(res.data['sugerencias'], ['Ventas del mes', 'Stock bajo'])
        self.assertIsNone(res.data['informe'])
        self.assertFalse(ReporteGenerado.objects.exists())

    def test_genera_informe_con_tabla_de_la_base(self):
        self.client.force_authenticate(self.empresa)
        self._consulta_y_presenta({'fuente': 'ventas_productos', 'agrupar_por': ['producto'],
                                   'metricas': ['unidades']})
        res = self.client.post(URL_GENERAR, mensajes('productos más vendidos'), format='json')

        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['tipo'], 'informe')
        informe = res.data['informe']
        self.assertEqual(informe['titulo'], 'Más vendidos')
        self.assertEqual(informe['filas'], [['Chompa de Alpaca', 3], ['Gorro andino', 1]])
        self.assertEqual(informe['grafico'], {'tipo': 'barras', 'etiqueta': 'producto', 'valor': 'unidades'})
        self.assertEqual(informe['tienda'], self.tienda.id)
        self.assertEqual(informe['notas'], [])
        self.assertEqual(res.data['sugerencias'], ['Ventas por semana'])

        guardado = ReporteGenerado.objects.get()
        self.assertEqual(guardado.generado_por_usuario, self.empresa)
        self.assertEqual(guardado.pregunta, 'productos más vendidos')

        # El modelo recibió el resultado de la consulta con su id.
        segunda_llamada = self.crear.call_args_list[1].kwargs['messages']
        self.assertIn('"consulta_id": 1', segunda_llamada[-1]['content'][0]['content'])

    def test_llamada_a_haiku_5_5_fija_el_esfuerzo_y_deja_margen_al_pensamiento(self):
        self.client.force_authenticate(self.empresa)
        self.crear.return_value = respuesta(texto('¿Qué periodo?'))
        self.client.post(URL_GENERAR, mensajes('quiero un informe'), format='json')

        llamada = self.crear.call_args.kwargs
        self.assertEqual(llamada['model'], 'claude-haiku-5-5')
        self.assertEqual(llamada['output_config'], {'effort': 'medium'})
        self.assertGreaterEqual(llamada['max_tokens'], 8000)
        for prohibido in ('temperature', 'top_p', 'thinking'):
            self.assertNotIn(prohibido, llamada)
        self.assertEqual(llamada['tool_choice'], {'type': 'auto'})

    def test_rechazo_del_modelo_devuelve_un_mensaje_claro(self):
        self.client.force_authenticate(self.empresa)
        self.crear.return_value = respuesta(texto('texto parcial'), stop_reason='refusal')
        res = self.client.post(URL_GENERAR, mensajes('algo que el modelo rechaza'), format='json')

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['tipo'], 'pregunta')
        self.assertIn('No puedo generar un informe', res.data['mensaje'])
        self.assertIsNone(res.data['informe'])
        self.assertFalse(ReporteGenerado.objects.exists())

    def test_los_bloques_de_pensamiento_se_reenvian_y_no_se_leen_como_texto(self):
        self.client.force_authenticate(self.empresa)
        pensamiento = SimpleNamespace(type='thinking', thinking='...', signature='firma')
        primera = respuesta(pensamiento, uso_herramienta('consultar_datos', {
            'fuente': 'pedidos', 'metricas': ['pedidos']}), stop_reason='tool_use')
        self.crear.side_effect = [primera, respuesta(pensamiento, texto('Tuviste **2 pedidos**.'))]

        res = self.client.post(URL_GENERAR, mensajes('cuántos pedidos'), format='json')

        self.assertEqual(res.data['informe']['analisis'], 'Tuviste **2 pedidos**.')
        reenviado = self.crear.call_args_list[1].kwargs['messages'][1]
        self.assertIs(reenviado['content'], primera.content)

    def test_el_modelo_no_puede_salir_de_las_tiendas_del_usuario(self):
        self.client.force_authenticate(self.empresa)
        self.crear.side_effect = [
            respuesta(uso_herramienta('consultar_datos', {
                'fuente': 'pedidos', 'metricas': ['pedidos'],
                'filtros': {'tienda_ids': [self.tienda_ajena.id]}}), stop_reason='tool_use'),
            respuesta(texto('No tengo acceso a esa tienda.\nSUGERENCIAS: Mis ventas')),
        ]
        res = self.client.post(URL_GENERAR, mensajes('ventas de Tienda Ajena'), format='json')
        self.assertEqual(res.data['tipo'], 'pregunta')
        resultado = self.crear.call_args_list[1].kwargs['messages'][-1]['content'][0]
        self.assertTrue(resultado['is_error'])

    def test_tienda_ajena_en_la_peticion_es_403(self):
        self.client.force_authenticate(self.empresa)
        datos = {**mensajes('ventas'), 'tienda_id': self.tienda_ajena.id}
        self.assertEqual(self.client.post(URL_GENERAR, datos, format='json').status_code, 403)
        self.crear.assert_not_called()

    def test_admin_ve_todas_las_tiendas(self):
        self.client.force_authenticate(self.admin)
        self._consulta_y_presenta({'fuente': 'pedidos', 'agrupar_por': ['tienda'], 'metricas': ['pedidos']})
        res = self.client.post(URL_GENERAR, mensajes('pedidos por tienda'), format='json')
        self.assertEqual(sorted(f[0] for f in res.data['informe']['filas']), ['Alpaca Andina', 'Tienda Ajena'])
        self.assertIsNone(res.data['informe']['tienda'])

    def test_si_contesta_en_texto_tras_consultar_igual_arma_el_informe(self):
        self.client.force_authenticate(self.empresa)
        self.crear.side_effect = [
            respuesta(uso_herramienta('consultar_datos', {'fuente': 'pedidos', 'metricas': ['pedidos']}),
                      stop_reason='tool_use'),
            respuesta(texto('Tuviste **2 pedidos**.')),
        ]
        res = self.client.post(URL_GENERAR, mensajes('cuántos pedidos'), format='json')
        self.assertEqual(res.data['tipo'], 'informe')
        self.assertEqual(res.data['informe']['filas'], [[2]])

    def test_sin_clave_responde_503(self):
        self.client.force_authenticate(self.empresa)
        with override_settings(ANTHROPIC_API_KEY=''):
            res = self.client.post(URL_GENERAR, mensajes('ventas'), format='json')
        self.assertEqual(res.status_code, 503)

    def test_historial_exportacion_y_borrado_solo_del_dueno(self):
        self.client.force_authenticate(self.empresa)
        self._consulta_y_presenta({'fuente': 'ventas_productos', 'agrupar_por': ['producto'],
                                   'metricas': ['unidades', 'ingresos']})
        informe_id = self.client.post(URL_GENERAR, mensajes('más vendidos'), format='json').data['informe']['id']

        lista = self.client.get(URL_LISTA)
        self.assertEqual([i['id'] for i in lista.data], [informe_id])

        pdf = self.client.get(f'{URL_LISTA}{informe_id}/exportar/?formato=pdf')
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf['Content-Type'], 'application/pdf')
        self.assertTrue(pdf.content.startswith(b'%PDF'))

        xlsx = self.client.get(f'{URL_LISTA}{informe_id}/exportar/?formato=xlsx')
        self.assertEqual(xlsx.status_code, 200)
        self.assertIn('attachment', xlsx['Content-Disposition'])

        self.client.force_authenticate(self.otra_empresa)
        self.assertEqual(self.client.get(f'{URL_LISTA}{informe_id}/').status_code, 404)
        self.assertEqual(self.client.get(f'{URL_LISTA}{informe_id}/exportar/').status_code, 404)

        self.client.force_authenticate(self.empresa)
        self.assertEqual(self.client.delete(f'{URL_LISTA}{informe_id}/').status_code, 204)
        self.assertFalse(ReporteGenerado.objects.exists())


class ExportarTests(BaseInformes):
    def _informe(self, **extra):
        datos = {
            'columnas': [
                {'clave': 'producto', 'titulo': 'Producto', 'tipo': 'texto', 'sumable': False},
                {'clave': 'unidades', 'titulo': 'Unidades vendidas', 'tipo': 'entero', 'sumable': True},
                {'clave': 'ingresos', 'titulo': 'Ingresos (Bs)', 'tipo': 'moneda', 'sumable': True},
                {'clave': 'pedidos', 'titulo': 'Pedidos', 'tipo': 'entero', 'sumable': False},
            ],
            'filas': [['Chompa “premium” de Alpaca 🦙', 3, 1050.0, 2], ['Gorro andino', 1, 80.0, 1]],
            'total_filas': 2, 'truncado': False, 'filtros': 'Periodo: 2026-09-01 a 2026-09-30',
        }
        return ReporteGenerado.objects.create(
            tienda=self.tienda, generado_por_usuario=self.empresa, tipo_reporte='informe_ia', formato='tabla',
            titulo='Más vendidos de septiembre', pregunta='más vendidos', datos=datos,
            analisis='### Hallazgos\n- La **chompa** lidera con 3 unidades.\n1. Repón stock.',
            grafico={'tipo': 'barras', 'etiqueta': 'producto', 'valor': 'ingresos'}, **extra)

    def test_pdf_con_caracteres_fuera_de_latin1(self):
        self.assertTrue(generar_pdf(self._informe()).startswith(b'%PDF'))

    def test_xlsx_tiene_datos_total_grafico_y_analisis(self):
        libro = load_workbook(BytesIO(generar_xlsx(self._informe())))
        hoja = libro['Datos']
        self.assertEqual(hoja['A5'].value, 'Producto')
        self.assertEqual(hoja['C6'].value, 1050.0)
        self.assertEqual(hoja['C8'].value, '=SUBTOTAL(109,C6:C7)')
        # Un pedido con varios productos aparece en varias filas: no se suma.
        self.assertIsNone(hoja['D8'].value)
        self.assertEqual(len(hoja._charts), 1)
        self.assertIn('Análisis', libro.sheetnames)

    def test_formato_de_porcentajes_y_variaciones(self):
        self.assertEqual(_formato(12.34, 'porcentaje'), '12,3 %')
        self.assertEqual(_formato(-39.74, 'variacion'), '-39,7 %')
        self.assertEqual(_formato(5.0, 'variacion'), '+5,0 %')
        self.assertEqual(_formato(-13.33, 'puntos'), '-13,3 pp')

    def test_pdf_y_xlsx_con_columnas_de_comparacion_y_notas(self):
        informe = self._informe()
        informe.datos = {
            'columnas': [
                {'clave': 'ticket', 'titulo': 'Ticket promedio (Bs)', 'tipo': 'moneda', 'sumable': False},
                {'clave': 'ticket_anterior', 'titulo': 'Ticket · periodo anterior', 'tipo': 'moneda',
                 'sumable': False},
                {'clave': 'ticket_variacion', 'titulo': 'Ticket · variación (%)', 'tipo': 'variacion',
                 'sumable': False},
                {'clave': 'tasa', 'titulo': 'Tasa (%)', 'tipo': 'porcentaje', 'sumable': False},
            ],
            'filas': [[235.0, 390.0, -39.74, 20.0]], 'total_filas': 1, 'truncado': False,
            'filtros': 'Periodo: 2026-11-01 a 2026-11-15', 'notas': ['El 8.5 % de las ventas no tiene costo.'],
        }
        informe.grafico = {}
        self.assertTrue(generar_pdf(informe).startswith(b'%PDF'))

        hoja = load_workbook(BytesIO(generar_xlsx(informe)))['Datos']
        self.assertEqual(hoja['C6'].value, -39.74)
        self.assertIn('+', hoja['C6'].number_format)
        self.assertIn('%', hoja['D6'].number_format)
        self.assertIn('8.5 %', hoja['A4'].value)

    def test_markdown_a_lineas(self):
        lineas = _lineas_markdown('### Título\n- uno **dos** [link](x)\n2) tres')
        self.assertEqual(lineas, [('titulo', 'Título'), ('vineta', '- uno **dos** link'), ('vineta', '2) tres')])


def momento(mes, dia, hora=12):
    return timezone.make_aware(datetime(2026, mes, dia, hora))


NOVIEMBRE = {'fecha_desde': '2026-11-01', 'fecha_hasta': '2026-11-15'}


class BaseKpis(BaseInformes):
    """Datos fechados para los KPI.

    Periodo actual: 1 al 15 de noviembre de 2026. Periodo anterior (el de igual
    duración justo antes): 17 al 31 de octubre. Los pedidos de `BaseInformes`
    quedan en enero. Costos: la chompa cuesta 200 y el gorro 30, salvo la venta
    de c3 (`venta_sin_costo`), que no tiene costo cargado.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        rol = Rol.objects.get(nombre='cliente')
        cls.c1 = cls.cliente
        cls.c2 = Usuario.objects.create_user(email='c2-inf@example.com', password='Password123!', rol=rol)
        cls.c3 = Usuario.objects.create_user(email='c3-inf@example.com', password='Password123!', rol=rol)

        Pedido.objects.update(fecha=momento(1, 10))
        for variante in (cls.chompa, cls.gorro, cls.ajena):
            Variante.objects.filter(pk=variante.pk).update(stock=100)
        categoria = Categoria.objects.get(tienda=cls.tienda, nombre='Textiles')
        cls.poncho = cls._variante(cls.tienda, categoria, 'Poncho', Decimal('500.00'), stock=7)

        chompa, gorro = cls.chompa, cls.gorro
        cls.venta_1 = cls._venta(cls.c1, [(chompa, 1, 200)], momento(11, 3))
        cls.venta_2 = cls._venta(cls.c2, [(gorro, 2, 30)], momento(11, 5))
        cls.venta_sin_costo = cls._venta(cls.c3, [(gorro, 1, None)], momento(11, 10))
        cls.venta_4 = cls._venta(cls.c2, [(chompa, 1, 200)], momento(11, 12))
        cls._venta(cls.c1, [(gorro, 1, 30)], momento(11, 8), estado='cancelado')
        cls._venta(cls.c1, [(chompa, 2, 200)], momento(10, 20))
        cls._venta(cls.c1, [(gorro, 1, 30)], momento(10, 25))
        cls._venta(cls.c2, [(gorro, 1, 30)], momento(10, 28), estado='cancelado')
        venta_ajena = cls._venta(cls.c3, [(cls.ajena, 5, 500)], momento(11, 11), tienda=cls.tienda_ajena)

        cls._entregar(cls.venta_1, inicio=momento(11, 3), entrega=momento(11, 5))
        cls._entregar(cls.venta_2, inicio=momento(11, 5), entrega=momento(11, 5, 18))
        cls._entregar(venta_ajena, inicio=momento(11, 11), entrega=momento(11, 16))

        for fecha, tienda, monto, categoria_gasto in (
            (momento(11, 2), cls.tienda, 100, 'alquiler'),
            (momento(11, 14), cls.tienda, 50, 'servicios'),
            (momento(10, 20), cls.tienda, 100, 'alquiler'),
            (momento(11, 20), cls.tienda, 999, 'otros'),
            (momento(11, 4), cls.tienda_ajena, 5000, 'sueldos'),
        ):
            GastoOperativo.objects.create(tienda=tienda, categoria=categoria_gasto, monto=monto,
                                          fecha=fecha.date())

        cls._eventos(cls.tienda, 'VIEW', 10)
        cls._eventos(cls.tienda, 'CART', 4)
        cls._eventos(cls.tienda_ajena, 'VIEW', 20)

        cls._uso_de_cupon(cls.tienda, 'PROMO10', [cls.venta_1, cls.venta_2])
        cls._uso_de_cupon(cls.tienda_ajena, 'AJENO', [venta_ajena])

        cls._recuperaciones(cls.tienda, [(cls.c1, None), (cls.c2, cls.venta_2), (cls.c3, None)])
        cls._recuperaciones(cls.tienda_ajena, [(cls.c3, venta_ajena)])

        for cliente, producto, nota in ((cls.c1, chompa.producto, 5), (cls.c2, chompa.producto, 5),
                                        (cls.c3, chompa.producto, 4), (cls.c1, gorro.producto, 2),
                                        (cls.c2, gorro.producto, 1)):
            Resena.objects.create(tienda=cls.tienda, cliente=cliente, producto=producto, calificacion=nota)
        Resena.objects.create(tienda=cls.tienda_ajena, cliente=cls.c1, producto=cls.ajena.producto, calificacion=1)

        # El stock final se fija al terminar: los triggers lo descuentan al vender.
        Variante.objects.filter(pk=chompa.pk).update(stock=10)
        Variante.objects.filter(pk=gorro.pk).update(stock=20)

    @classmethod
    def _venta(cls, cliente, lineas, fecha, tienda=None, estado='pendiente'):
        tienda = tienda or cls.tienda
        pedido = Pedido.objects.create(cliente=cliente, tienda=tienda, subtotal=0, total=0,
                                       estado_actual='pendiente')
        for variante, cantidad, costo in lineas:
            ItemPedido.objects.create(tienda=tienda, pedido=pedido, variante=variante, cantidad=cantidad,
                                      precio_unitario=variante.precio, costo_unitario=costo)
        Pedido.objects.filter(pk=pedido.pk).update(fecha=fecha, estado_actual=estado)
        pedido.refresh_from_db()
        return pedido

    @classmethod
    def _entregar(cls, pedido, inicio, entrega):
        Pedido.objects.filter(pk=pedido.pk).update(estado_actual='entregado')
        HistorialEstadoPedido.objects.filter(pedido=pedido, estado='pendiente').update(fecha=inicio)
        HistorialEstadoPedido.objects.filter(pedido=pedido, estado='entregado').update(fecha=entrega)

    @classmethod
    def _eventos(cls, tienda, tipo, cantidad):
        EventoUsuario.objects.bulk_create(
            [EventoUsuario(tienda=tienda, tipo_evento=tipo, cliente=cls.c1) for _ in range(cantidad)])
        EventoUsuario.objects.filter(tienda=tienda, tipo_evento=tipo).update(fecha=momento(11, 4))

    @classmethod
    def _uso_de_cupon(cls, tienda, codigo, pedidos):
        cupon = Cupon.objects.create(tienda=tienda, codigo=codigo, tipo_descuento='porcentaje',
                                     valor_descuento=10, fecha_expiracion=datetime(2027, 1, 1).date())
        for pedido in pedidos:
            uso = CuponUso.objects.create(tienda=tienda, cupon=cupon, pedido=pedido)
            CuponUso.objects.filter(pk=uso.pk).update(fecha_uso=pedido.fecha)

    @classmethod
    def _recuperaciones(cls, tienda, casos):
        campana = CampanaCarrito.objects.create(tienda=tienda, activo=True)
        for cliente, pedido in casos:
            carrito = Carrito.objects.create(cliente=cliente, tienda=tienda)
            registro = RegistroRecuperacionCarrito.objects.create(
                campana=campana, carrito=carrito, cliente=cliente, recuperado=pedido is not None,
                pedido_resultante=pedido)
            RegistroRecuperacionCarrito.objects.filter(pk=registro.pk).update(fecha_envio=momento(11, 6))


class KpiTests(BaseKpis):
    def _ejecutar(self, spec, tiendas=None):
        return consultas.ejecutar(consultas.normalizar(spec), tiendas or [self.tienda.id])

    def _claves(self, resultado):
        return [c['clave'] for c in resultado['columnas']]

    def test_ticket_promedio_y_variacion_frente_al_periodo_anterior(self):
        spec = {'fuente': 'pedidos', 'metricas': ['ticket_promedio'], 'filtros': NOVIEMBRE,
                'comparar_con': 'periodo_anterior'}
        r = self._ejecutar(spec)
        self.assertEqual(self._claves(r), ['ticket_promedio', 'ticket_promedio_anterior', 'ticket_promedio_variacion'])
        self.assertEqual([c['tipo'] for c in r['columnas']], ['moneda', 'moneda', 'variacion'])
        self.assertEqual(r['filas'], [[235.0, 390.0, -39.74]])
        self.assertIn('2026-10-17 a 2026-10-31', r['notas'][0])
        self.assertIn('Comparado con: periodo anterior (2026-10-17 a 2026-10-31)',
                      consultas.describir_filtros(consultas.normalizar(spec), {}))

    def test_comparar_con_el_mismo_periodo_del_anio_anterior(self):
        r = self._ejecutar({'fuente': 'pedidos', 'metricas': ['monto_total'], 'filtros': NOVIEMBRE,
                            'comparar_con': 'mismo_periodo_anio_anterior'})
        # Noviembre de 2025 no tiene ventas: no hay base para un porcentaje.
        self.assertEqual(r['filas'], [[940.0, 0.0, None]])

    def test_el_periodo_comparado_resuelve_el_29_de_febrero(self):
        desde, hasta = consultas._periodo_comparado(
            {'fecha_desde': '2028-02-29', 'fecha_hasta': '2028-03-01'}, 'mismo_periodo_anio_anterior')
        self.assertEqual((desde.isoformat(), hasta.isoformat()), ('2027-02-28', '2027-03-01'))

    def test_comparacion_por_producto_ordenada_por_variacion(self):
        r = self._ejecutar({'fuente': 'ventas_productos', 'agrupar_por': ['producto'], 'metricas': ['unidades'],
                            'filtros': NOVIEMBRE, 'comparar_con': 'periodo_anterior',
                            'ordenar_por': 'unidades_variacion'})
        self.assertEqual(r['filas'], [['Gorro andino', 3, 1, 200.0], ['Chompa de Alpaca', 2, 2, 0.0]])

    def test_variacion_de_un_porcentaje_se_expresa_en_puntos(self):
        r = self._ejecutar({'fuente': 'cancelaciones', 'metricas': ['tasa_cancelacion'], 'filtros': NOVIEMBRE,
                            'comparar_con': 'periodo_anterior'})
        self.assertEqual(r['columnas'][2]['tipo'], 'puntos')
        self.assertEqual(r['filas'], [[20.0, 33.33, -13.33]])

    def test_comparaciones_invalidas(self):
        base = {'fuente': 'pedidos', 'metricas': ['pedidos'], 'filtros': NOVIEMBRE,
                'comparar_con': 'periodo_anterior'}
        casos = [
            {**base, 'filtros': {}},
            {**base, 'filtros': {'fecha_desde': '2026-11-01'}},
            {**base, 'agrupar_por': ['mes']},
            {**base, 'metricas': ['pedidos', 'monto_total', 'ticket_promedio', 'clientes']},
            {**base, 'metricas': ['ultima_compra']},
            {**base, 'comparar_con': 'ayer'},
            {**base, 'comparar_con': None, 'ordenar_por': 'pedidos_variacion'},
            {**base, 'filtros': {'fecha_desde': '2026-11-15', 'fecha_hasta': '2026-11-01'}},
        ]
        for spec in casos:
            with self.subTest(spec=spec), self.assertRaises(consultas.ConsultaInvalida):
                consultas.normalizar(spec)

    def test_clientes_nuevos_recurrentes_y_tasa_de_recompra(self):
        r = self._ejecutar({'fuente': 'clientes', 'filtros': NOVIEMBRE,
                            'metricas': ['clientes', 'clientes_nuevos', 'clientes_recurrentes', 'tasa_recompra']})
        # c1 ya había comprado en enero; c2 y c3 compran por primera vez en el periodo.
        self.assertEqual(r['filas'], [[3, 2, 1, 33.33]])

    def test_kpis_que_necesitan_periodo_lo_exigen(self):
        for spec in ({'fuente': 'clientes', 'metricas': ['clientes']},
                     {'fuente': 'rotacion_inventario', 'metricas': ['rotacion'],
                      'filtros': {'fecha_desde': '2026-11-01'}}):
            with self.subTest(spec=spec), self.assertRaises(consultas.ConsultaInvalida):
                consultas.normalizar(spec)

    def test_tasa_de_cancelacion(self):
        r = self._ejecutar({'fuente': 'cancelaciones', 'filtros': NOVIEMBRE,
                            'metricas': ['pedidos', 'cancelados', 'tasa_cancelacion', 'monto_cancelado']})
        self.assertEqual(r['filas'], [[5, 1, 20.0, 80.0]])
        self.assertEqual([c['sumable'] for c in r['columnas']], [True, True, False, True])
        self.assertEqual(r['columnas'][2]['mejor_si'], 'baja')

    def test_conversion_vista_carrito_compra(self):
        r = self._ejecutar({'fuente': 'embudo_conversion', 'filtros': NOVIEMBRE, 'metricas': [
            'vistas', 'carritos', 'compras', 'tasa_vista_a_carrito', 'tasa_carrito_a_compra',
            'tasa_vista_a_compra']})
        self.assertEqual(r['filas'], [[10, 4, 4, 40.0, 100.0, 40.0]])

    def test_embudo_por_mes_junta_eventos_y_pedidos(self):
        r = self._ejecutar({'fuente': 'embudo_conversion', 'agrupar_por': ['mes'],
                            'metricas': ['vistas', 'compras']})
        self.assertEqual(r['filas'], [['2026-01', 0, 2], ['2026-10', 0, 2], ['2026-11', 10, 4]])

    def test_tiempo_de_entrega_desde_el_historial_de_estados(self):
        r = self._ejecutar({'fuente': 'entregas', 'filtros': NOVIEMBRE, 'metricas': [
            'entregados', 'horas_entrega_promedio', 'dias_entrega_promedio', 'horas_entrega_maxima',
            'horas_entrega_minima']})
        # 48 h y 6 h: promedio 27 h (1,125 días).
        self.assertEqual(r['filas'], [[2, 27.0, 1.13, 48.0, 6.0]])

    def test_rotacion_de_inventario(self):
        r = self._ejecutar({'fuente': 'rotacion_inventario', 'agrupar_por': ['producto'], 'filtros': NOVIEMBRE,
                            'metricas': ['stock_actual', 'unidades_vendidas', 'rotacion', 'dias_de_inventario']})
        self.assertEqual(r['filas'], [
            ['Gorro andino', 20, 3, 0.15, 100.0],
            ['Chompa de Alpaca', 10, 2, 0.2, 75.0],
            ['Poncho', 7, 0, 0.0, None],
        ])

    def test_carritos_recuperados(self):
        r = self._ejecutar({'fuente': 'carritos_recuperados', 'filtros': NOVIEMBRE, 'metricas': [
            'notificaciones', 'recuperados', 'tasa_recuperacion', 'ingresos_recuperados']})
        self.assertEqual(r['filas'], [[3, 1, 33.33, 160.0]])

    def test_uso_de_cupones(self):
        r = self._ejecutar({'fuente': 'cupones', 'filtros': NOVIEMBRE, 'metricas': [
            'usos', 'pedidos_con_cupon', 'ventas_con_cupon', 'pedidos_totales', 'tasa_uso_cupon']})
        self.assertEqual(r['filas'], [[2, 2, 510.0, 4, 50.0]])
        por_cupon = self._ejecutar({'fuente': 'cupones', 'agrupar_por': ['cupon'], 'metricas': ['usos']})
        self.assertEqual(por_cupon['filas'], [['PROMO10', 2]])
        with self.assertRaises(consultas.ConsultaInvalida):
            consultas.normalizar({'fuente': 'cupones', 'agrupar_por': ['cupon'], 'metricas': ['tasa_uso_cupon']})

    def test_distribucion_de_calificaciones(self):
        r = self._ejecutar({'fuente': 'resenas', 'agrupar_por': ['calificacion'],
                            'metricas': ['resenas', 'participacion_resenas'], 'ordenar_por': 'calificacion',
                            'descendente': True})
        self.assertEqual(r['filas'], [[5, 2, 40.0], [4, 1, 20.0], [2, 1, 20.0], [1, 1, 20.0]])
        total = self._ejecutar({'fuente': 'resenas', 'metricas': ['pct_positivas', 'pct_negativas']})
        self.assertEqual(total['filas'], [[60.0, 40.0]])

    def test_ganancia_margen_gastos_y_utilidad_neta(self):
        r = self._ejecutar({'fuente': 'resultados', 'filtros': NOVIEMBRE, 'metricas': [
            'ingresos', 'ganancia_bruta', 'margen_bruto_pct', 'gastos_operativos', 'utilidad_neta',
            'ventas_sin_costo_pct']})
        # Con costo: 350 + 160 + 350 = 860 de ingresos y 460 de costo. Sin costo: 80 (8,51 %).
        self.assertEqual(r['filas'], [[940.0, 400.0, 46.51, 150.0, 250.0, 8.51]])
        self.assertEqual(len(r['notas']), 1)
        self.assertIn('8.5 % de las ventas (Bs 80.00 de Bs 940.00) no tiene costo cargado', r['notas'][0])

    def test_cuanto_gane_en_estos_productos_descontando_gastos(self):
        r = self._ejecutar({'fuente': 'resultados', 'filtros': {**NOVIEMBRE, 'producto': 'Gorro'},
                            'metricas': ['ingresos', 'ganancia_bruta', 'gastos_operativos', 'utilidad_neta']})
        self.assertEqual(r['filas'], [[240.0, 100.0, 150.0, -50.0]])
        self.assertTrue(any('toda la tienda' in nota for nota in r['notas']))
        self.assertTrue(any('33.3 %' in nota for nota in r['notas']))

    def test_utilidad_por_mes_junta_ventas_y_gastos(self):
        r = self._ejecutar({'fuente': 'resultados', 'agrupar_por': ['mes'],
                            'metricas': ['ganancia_bruta', 'gastos_operativos', 'utilidad_neta'],
                            'filtros': {'fecha_desde': '2026-10-01', 'fecha_hasta': '2026-11-30'}})
        # Octubre: ganancia 350 - gasto 100. Noviembre: 400 - (100 + 50 + 999).
        self.assertEqual(r['filas'], [['2026-10', 350.0, 100.0, 250.0], ['2026-11', 400.0, 1149.0, -749.0]])

    def test_el_costo_faltante_no_se_trata_como_cero(self):
        dia = {'fecha_desde': '2026-11-10', 'fecha_hasta': '2026-11-10'}
        r = self._ejecutar({'fuente': 'ventas_productos', 'filtros': dia,
                            'metricas': ['ingresos', 'ganancia_bruta', 'margen_bruto_pct',
                                         'ventas_sin_costo_pct']})
        # Solo se vendió un gorro sin costo: no hay ganancia calculable, no "ganancia 80".
        self.assertEqual(r['filas'], [[80.0, 0.0, None, 100.0]])
        self.assertIn('Ninguna venta del periodo tiene costo cargado', r['notas'][0])

    def test_si_todo_tiene_costo_lo_dice(self):
        r = self._ejecutar({'fuente': 'ventas_productos', 'metricas': ['ganancia_bruta'],
                            'filtros': {'fecha_desde': '2026-10-17', 'fecha_hasta': '2026-10-31'}})
        self.assertEqual(r['filas'], [[350.0]])
        self.assertEqual(r['notas'], ['Todas las ventas del periodo tienen costo cargado.'])

    def test_ganancia_por_producto_y_participacion(self):
        r = self._ejecutar({'fuente': 'ventas_productos', 'agrupar_por': ['producto'], 'filtros': NOVIEMBRE,
                            'metricas': ['ingresos', 'ganancia_bruta', 'participacion_ingresos']})
        self.assertEqual(r['filas'], [['Chompa de Alpaca', 700.0, 300.0, 74.47],
                                      ['Gorro andino', 240.0, 100.0, 25.53]])

    def test_gastos_por_categoria(self):
        r = self._ejecutar({'fuente': 'gastos', 'agrupar_por': ['categoria_gasto'], 'filtros': NOVIEMBRE,
                            'metricas': ['gastos']})
        self.assertEqual(r['filas'], [['Alquiler', 100.0], ['Servicios básicos', 50.0]])

    def test_dimension_que_la_metrica_no_soporta(self):
        with self.assertRaises(consultas.ConsultaInvalida) as ctx:
            consultas.normalizar({'fuente': 'resultados', 'agrupar_por': ['producto'],
                                  'metricas': ['utilidad_neta']})
        self.assertIn('no se puede desglosar por producto', str(ctx.exception))
        r = self._ejecutar({'fuente': 'resultados', 'agrupar_por': ['producto'], 'filtros': NOVIEMBRE,
                            'metricas': ['ganancia_bruta']})
        self.assertEqual([f[0] for f in r['filas']], ['Chompa de Alpaca', 'Gorro andino'])

    def test_las_fuentes_nuevas_solo_ven_las_tiendas_permitidas(self):
        casos = [
            {'fuente': 'pedidos', 'metricas': ['monto_total']},
            {'fuente': 'resultados', 'metricas': ['ingresos']},
            {'fuente': 'gastos', 'metricas': ['gastos']},
            {'fuente': 'cancelaciones', 'metricas': ['pedidos']},
            {'fuente': 'clientes', 'metricas': ['pedidos'], 'filtros': NOVIEMBRE},
            {'fuente': 'embudo_conversion', 'metricas': ['vistas']},
            {'fuente': 'entregas', 'metricas': ['entregados']},
            {'fuente': 'rotacion_inventario', 'metricas': ['stock_actual'], 'filtros': NOVIEMBRE},
            {'fuente': 'carritos_recuperados', 'metricas': ['notificaciones']},
            {'fuente': 'cupones', 'metricas': ['usos']},
            {'fuente': 'resenas', 'metricas': ['resenas']},
        ]
        ambas = [self.tienda.id, self.tienda_ajena.id]
        for spec in casos:
            with self.subTest(fuente=spec['fuente']):
                propia = self._ejecutar(spec)['filas']
                self.assertNotEqual(propia, self._ejecutar(spec, ambas)['filas'])
                self.assertNotEqual(propia, self._ejecutar(spec, [self.tienda_ajena.id])['filas'])

    def test_ventas_por_mes_salen_en_orden_cronologico_ascendente(self):
        pedidos = {'fuente': 'pedidos', 'agrupar_por': ['mes'], 'metricas': ['monto_total']}
        esperado = [['2026-01', 1130.0], ['2026-10', 780.0], ['2026-11', 940.0]]
        for extra in ({}, {'ordenar_por': 'mes'}, {'ordenar_por': 'mes', 'descendente': False}):
            with self.subTest(extra=extra):
                self.assertEqual(self._ejecutar({**pedidos, **extra})['filas'], esperado)
        self.assertEqual(self._ejecutar({**pedidos, 'ordenar_por': 'mes', 'descendente': True})['filas'],
                         esperado[::-1])
        self.assertEqual(self._ejecutar({**pedidos, 'ordenar_por': 'monto_total'})['filas'],
                         [['2026-01', 1130.0], ['2026-11', 940.0], ['2026-10', 780.0]])

    def test_dos_columnas_con_tiempo_ordenan_por_el_tiempo(self):
        r = self._ejecutar({'fuente': 'ventas_productos', 'agrupar_por': ['producto', 'mes'],
                            'metricas': ['unidades'],
                            'filtros': {'fecha_desde': '2026-10-01', 'fecha_hasta': '2026-11-30'}})
        self.assertEqual([f[1] for f in r['filas']], ['2026-10', '2026-10', '2026-11', '2026-11'])


@override_settings(ANTHROPIC_API_KEY='sk-ant-test', INFORMES_MODEL='claude-haiku-5-5')
class InformesKpiApiTests(ClaudeSimulado, BaseKpis):
    def test_serie_mensual_pedida_por_el_modelo_llega_en_orden_cronologico(self):
        self.client.force_authenticate(self.empresa)
        self._consulta_y_presenta(
            {'fuente': 'pedidos', 'agrupar_por': ['mes'], 'metricas': ['monto_total'], 'ordenar_por': 'mes'},
            grafico={'tipo': 'lineas', 'etiqueta': 'mes', 'valor': 'monto_total'})
        res = self.client.post(URL_GENERAR, mensajes('ventas por mes ordenadas por mes'), format='json')

        self.assertEqual([f[0] for f in res.data['informe']['filas']], ['2026-01', '2026-10', '2026-11'])
        self.assertEqual(res.data['informe']['grafico']['tipo'], 'lineas')

    def test_el_informe_guarda_las_notas_y_el_modelo_las_recibe(self):
        self.client.force_authenticate(self.empresa)
        self._consulta_y_presenta(
            {'fuente': 'resultados', 'metricas': ['ganancia_bruta', 'utilidad_neta'], 'filtros': NOVIEMBRE},
            grafico={'tipo': 'barras', 'etiqueta': 'ganancia_bruta', 'valor': 'utilidad_neta'})
        res = self.client.post(URL_GENERAR, mensajes('cuánto gané del 1 al 15 de noviembre'), format='json')

        informe = res.data['informe']
        self.assertEqual(informe['filas'], [[400.0, 250.0]])
        self.assertIn('no tiene costo cargado', informe['notas'][0])
        resultado = self.crear.call_args_list[1].kwargs['messages'][-1]['content'][0]['content']
        self.assertIn('no tiene costo cargado', resultado)
        self.assertEqual(ReporteGenerado.objects.get().datos['notas'], informe['notas'])

    def test_comparacion_de_periodos_a_traves_de_la_api(self):
        self.client.force_authenticate(self.empresa)
        self._consulta_y_presenta(
            {'fuente': 'pedidos', 'metricas': ['ticket_promedio'], 'filtros': NOVIEMBRE,
             'comparar_con': 'periodo_anterior'},
            grafico={'tipo': 'ninguno'})
        res = self.client.post(URL_GENERAR, mensajes('ticket promedio frente al periodo anterior'), format='json')

        informe = res.data['informe']
        self.assertEqual([c['clave'] for c in informe['columnas']],
                         ['ticket_promedio', 'ticket_promedio_anterior', 'ticket_promedio_variacion'])
        self.assertEqual(informe['filas'], [[235.0, 390.0, -39.74]])
        self.assertIn('Comparado con: periodo anterior', informe['filtros'])

    def test_consulta_con_comparacion_invalida_devuelve_el_error_al_modelo(self):
        self.client.force_authenticate(self.empresa)
        self.crear.side_effect = [
            respuesta(uso_herramienta('consultar_datos', {
                'fuente': 'pedidos', 'metricas': ['pedidos'], 'comparar_con': 'periodo_anterior'}),
                stop_reason='tool_use'),
            respuesta(texto('¿De qué periodo?\nSUGERENCIAS: Este mes')),
        ]
        self.client.post(URL_GENERAR, mensajes('compara las ventas'), format='json')
        resultado = self.crear.call_args_list[1].kwargs['messages'][-1]['content'][0]
        self.assertTrue(resultado['is_error'])
        self.assertIn('fecha_desde', resultado['content'])
