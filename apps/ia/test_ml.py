"""Pruebas de los modelos de Machine Learning (numpy) y de sus endpoints.

Los algoritmos se prueban con datos sintéticos pequeños de patrón conocido. Los
endpoints, con una tienda de la base de pruebas armada con semilla fija.
"""

import random
from dataclasses import replace
from datetime import datetime, time, timedelta
from decimal import Decimal
from io import StringIO

import numpy as np
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.catalogo.models import Producto, Variante
from apps.marketing.models import Cupon, CuponUso
from apps.pedidos.models import ItemPedido, Pedido, Resena
from apps.tiendas.models import Tienda
from apps.usuarios.models import Permiso, Rol, RolPermiso, Usuario

from .ml import abandono, compras_conjuntas, pronostico
from .ml import datos as carga
from .ml.entrenamiento import entrenar_tienda
from .models import EventoUsuario, ModeloML


def url_ml(tienda_id):
    return f'/api/ia/ml/tiendas/{tienda_id}/'


def url_entrenar(tienda_id):
    return f'/api/ia/ml/tiendas/{tienda_id}/entrenar/'


class PronosticoTests(SimpleTestCase):
    def _serie(self, n=200, ruido=3.0):
        azar = np.random.default_rng(1)
        dias = np.arange(738000, 738000 + n)
        efecto_semana = np.array([0, 5, 10, 8, 15, 30, 40.0])[(dias - 1) % 7]
        ingresos = 100 + 0.8 * np.arange(n) + efecto_semana + azar.normal(0, ruido, n)
        return dias, ingresos

    def test_ridge_recupera_coeficientes_conocidos(self):
        azar = np.random.default_rng(0)
        X = np.column_stack([np.ones(300), azar.normal(size=300), azar.normal(size=300)])
        y = X @ np.array([4.0, 2.0, -3.0]) + azar.normal(0, 0.01, 300)
        np.testing.assert_allclose(pronostico.ajustar_ridge(X, y, 0.0), [4.0, 2.0, -3.0], atol=0.01)

    def test_ridge_no_penaliza_la_constante(self):
        X = np.column_stack([np.ones(50), np.linspace(-1, 1, 50)])
        pesos = pronostico.ajustar_ridge(X, np.full(50, 7.0), 1000.0)
        self.assertAlmostEqual(pesos[0], 7.0, places=6)
        self.assertAlmostEqual(pesos[1], 0.0, places=6)

    def test_recupera_la_tendencia_y_el_dia_de_la_semana(self):
        dias, ingresos = self._serie()
        resultado = pronostico.pronosticar(dias, ingresos)['resultados']['pronostico']
        futuros = np.arange(dias[-1] + 1, dias[-1] + 31)
        esperado = 100 + 0.8 * np.arange(200, 230) + np.array([0, 5, 10, 8, 15, 30, 40.0])[(futuros - 1) % 7]
        error_relativo = np.abs(np.array(resultado['valores']) - esperado) / esperado
        self.assertLess(error_relativo.mean(), 0.05)
        self.assertEqual(len(resultado['fechas']), 30)

    def test_la_banda_contiene_al_pronostico_y_no_baja_de_cero(self):
        dias, ingresos = self._serie()
        r = pronostico.pronosticar(dias, ingresos)['resultados']['pronostico']
        for inferior, central, superior in zip(r['inferior'], r['valores'], r['superior']):
            self.assertGreaterEqual(inferior, 0)
            self.assertLessEqual(inferior, central)
            self.assertLessEqual(central, superior)

    def test_supera_a_la_linea_base_y_las_metricas_estan_en_rango(self):
        dias, ingresos = self._serie()
        metricas = pronostico.evaluar(dias, ingresos)['metricas']
        self.assertLess(metricas['mae'], metricas['mae_base'])
        self.assertGreater(metricas['mejora_mae_pct'], 0)
        self.assertGreaterEqual(metricas['mape'], 0)
        self.assertTrue(0 <= metricas['cobertura_intervalo_pct'] <= 100)
        self.assertEqual(metricas['dias_validacion'], 28)

    def test_es_reproducible(self):
        dias, ingresos = self._serie()
        self.assertEqual(pronostico.evaluar(dias, ingresos), pronostico.evaluar(dias, ingresos))
        self.assertEqual(pronostico.pronosticar(dias, ingresos), pronostico.pronosticar(dias, ingresos))


class AbandonoTests(SimpleTestCase):
    def test_auc_con_valores_conocidos(self):
        y = np.array([0, 0, 1, 1.0])
        self.assertAlmostEqual(abandono.auc(y, np.array([0.1, 0.4, 0.35, 0.8])), 0.75)
        self.assertAlmostEqual(abandono.auc(y, np.array([0.1, 0.2, 0.8, 0.9])), 1.0)
        self.assertAlmostEqual(abandono.auc(y, np.array([0.5, 0.5, 0.5, 0.5])), 0.5)

    def test_la_logistica_separa_dos_grupos(self):
        azar = np.random.default_rng(3)
        X = np.vstack([azar.normal(-1.5, 1, (150, 3)), azar.normal(1.5, 1, (150, 3))])
        y = np.concatenate([np.zeros(150), np.ones(150)])
        pesos, sesgo = abandono.ajustar_logistica(X, y)
        probabilidad = 1 / (1 + np.exp(-(X @ pesos + sesgo)))
        self.assertGreater(abandono.auc(y, probabilidad), 0.95)
        self.assertTrue(np.all(pesos > 0))
        self.assertGreater(((probabilidad >= 0.5) == (y == 1)).mean(), 0.9)

    def test_particion_estratificada(self):
        y = np.concatenate([np.zeros(80), np.ones(20)])
        entrenamiento, prueba = abandono.particion_estratificada(y, 0.25, 42)
        self.assertEqual(len(entrenamiento) + len(prueba), 100)
        self.assertEqual(set(entrenamiento) & set(prueba), set())
        self.assertEqual(y[prueba].sum(), 5)
        self.assertEqual(len(prueba), 25)
        otra = abandono.particion_estratificada(y, 0.25, 42)
        np.testing.assert_array_equal(prueba, otra[1])


class ComprasConjuntasTests(SimpleTestCase):
    def _canastas(self):
        azar = random.Random(5)
        canastas = [frozenset({1, 2})] * 25 + [frozenset({3, 4})] * 25
        canastas += [frozenset({azar.choice([5, 6, 7, 8, 9, 10])}) for _ in range(150)]
        azar.shuffle(canastas)
        return canastas

    def test_detecta_el_par_fijo(self):
        reglas = compras_conjuntas.Reglas(self._canastas())
        pares = compras_conjuntas.pares_principales(reglas, {1: 'A', 2: 'B', 3: 'C', 4: 'D'})
        self.assertEqual({frozenset((f['producto_a'], f['producto_b'])) for f in pares},
                         {frozenset('AB'), frozenset('CD')})
        par = next(f for f in pares if {f['producto_a'], f['producto_b']} == set('AB'))
        self.assertEqual(par['pedidos'], 25)
        self.assertEqual(par['confianza_a_b'], 1.0)
        self.assertEqual(par['soporte'], 0.125)
        self.assertGreater(par['lift'], 1)

    def test_recomienda_el_companero(self):
        reglas = compras_conjuntas.Reglas(self._canastas())
        self.assertEqual(reglas.recomendar(frozenset({1}), 5), [2])
        self.assertEqual(reglas.recomendar(frozenset({7}), 5), [])

    def test_hit_rate_supera_a_la_popularidad_cuando_hay_patron(self):
        metricas = compras_conjuntas.evaluar(self._canastas())
        self.assertGreater(metricas['pedidos_prueba'], 0)
        self.assertEqual(metricas['hit_rate_5'], 1.0)
        self.assertLess(metricas['hit_rate_5_populares'], metricas['hit_rate_5'])

    def test_es_reproducible(self):
        canastas = self._canastas()
        self.assertEqual(compras_conjuntas.evaluar(canastas), compras_conjuntas.evaluar(canastas))


class BaseTiendaMl(APITestCase):
    @classmethod
    def setUpTestData(cls):
        rol_empresa = Rol.objects.get_or_create(nombre='empresa')[0]
        rol_admin = Rol.objects.get_or_create(nombre='administrador')[0]
        rol_cliente = Rol.objects.get_or_create(nombre='cliente')[0]
        cls.empresa = Usuario.objects.create_user(
            email='empresa-ml@example.com', password='Password123!', rol=rol_empresa)
        cls.otra_empresa = Usuario.objects.create_user(
            email='otra-ml@example.com', password='Password123!', rol=rol_empresa)
        cls.admin = Usuario.objects.create_user(
            email='admin-ml@example.com', password='Password123!', rol=rol_admin)
        cls.sin_permiso = Usuario.objects.create_user(
            email='cliente-ml@example.com', password='Password123!', rol=rol_cliente)

        cls.tienda = Tienda.objects.create(propietario=cls.empresa, nombre='Tienda ML')
        cls.tienda_vacia = Tienda.objects.create(propietario=cls.empresa, nombre='Tienda sin ventas')
        cls.tienda_ajena = Tienda.objects.create(propietario=cls.otra_empresa, nombre='Tienda ajena')

        cls.variantes = []
        for i, nombre in enumerate(['Poncho', 'Bufanda', 'Quinua', 'Café', 'Miel', 'Gorro']):
            producto = Producto.objects.create(tienda=cls.tienda, nombre=nombre, slug=f'ml-{i}')
            cls.variantes.append(Variante.objects.create(
                producto=producto, sku=f'ML-{i}', precio=Decimal('50.00'), stock=10 ** 6, stock_minimo=0))
        cls._sembrar_ventas()

    @classmethod
    def _sembrar_ventas(cls):
        azar = random.Random(7)
        hoy = timezone.localdate()
        rol_cliente = Rol.objects.get(nombre='cliente')
        clientes = Usuario.objects.bulk_create([
            Usuario(email=f'c{i}-ml@example.com', password='!', rol=rol_cliente) for i in range(90)])
        cupon = Cupon.objects.create(
            tienda=cls.tienda, codigo='ML10', tipo_descuento='porcentaje', valor_descuento=10,
            fecha_expiracion=hoy + timedelta(days=30))
        pedidos, lineas, con_cupon = [], [], []
        for i, cliente in enumerate(clientes):
            for _ in range(azar.randint(1, 6)):
                # Poncho y bufanda se compran juntos en 4 de cada 10 pedidos.
                elegidas = [0, 1] if azar.random() < 0.4 else azar.sample(range(6), azar.randint(1, 2))
                pedidos.append(Pedido(
                    cliente=cliente, tienda=cls.tienda, subtotal=0, total=0, estado_actual='entregado'))
                lineas.append(elegidas)
                con_cupon.append(i % 10 == 0)
            if i % 3 == 0:
                Resena.objects.create(tienda=cls.tienda, cliente=cliente, calificacion=azar.randint(1, 5))
        pedidos = Pedido.objects.bulk_create(pedidos)
        for pedido in pedidos:
            pedido.fecha = timezone.make_aware(
                datetime.combine(hoy - timedelta(days=azar.randint(0, 160)), time(12)))
        Pedido.objects.bulk_update(pedidos, ['fecha'])
        ItemPedido.objects.bulk_create([
            ItemPedido(tienda=cls.tienda, pedido=pedido, variante=cls.variantes[k],
                       cantidad=azar.randint(1, 3), precio_unitario=cls.variantes[k].precio)
            for pedido, elegidas in zip(pedidos, lineas) for k in elegidas])
        CuponUso.objects.bulk_create([
            CuponUso(tienda=cls.tienda, cupon=cupon, pedido=pedido)
            for pedido, usado in zip(pedidos, con_cupon) if usado])
        EventoUsuario.objects.bulk_create([
            EventoUsuario(cliente=azar.choice(clientes), tienda=cls.tienda, tipo_evento='VIEW')
            for _ in range(200)])


class DatosYVariablesTests(BaseTiendaMl):
    def test_los_cancelados_no_entran(self):
        cancelado = Pedido.objects.create(
            cliente=self.sin_permiso, tienda=self.tienda, subtotal=0, total=0, estado_actual='cancelado')
        datos = carga.cargar(self.tienda)
        self.assertNotIn(cancelado.id, datos.pedido_id)
        self.assertEqual(datos.pedido_id.shape, datos.pedido_cliente.shape)

    def test_las_variables_no_ven_datos_posteriores_al_corte(self):
        datos = carga.cargar(self.tienda)
        corte = datos.hasta - timedelta(days=59)
        clientes, X = abandono.variables_clientes(datos, corte)

        futuros = np.flatnonzero(datos.pedido_dia >= corte.toordinal())
        self.assertGreater(len(futuros), 0)
        inflado = replace(
            datos,
            pedido_total=np.where(datos.pedido_dia >= corte.toordinal(), 1e9, datos.pedido_total),
            resena_calificacion=np.where(datos.resena_dia >= corte.toordinal(), 1.0, datos.resena_calificacion),
        )
        clientes_2, X_2 = abandono.variables_clientes(inflado, corte)
        np.testing.assert_array_equal(clientes, clientes_2)
        np.testing.assert_array_equal(X, X_2)

    def test_la_etiqueta_es_no_comprar_en_la_ventana(self):
        datos = carga.cargar(self.tienda)
        corte = datos.hasta - timedelta(days=59)
        clientes, _ = abandono.variables_clientes(datos, corte)
        y = abandono.etiquetas_abandono(datos, clientes, corte, datos.hasta)
        compraron = set(datos.pedido_cliente[datos.pedido_dia >= corte.toordinal()].tolist())
        self.assertEqual({int(c) for c, e in zip(clientes, y) if e == 0}, compraron & set(clientes.tolist()))

    def test_serie_diaria_cubre_cada_dia_hasta_hoy(self):
        datos = carga.cargar(self.tienda)
        dias, ingresos = carga.serie_diaria(datos)
        self.assertEqual(dias[-1], datos.hasta.toordinal())
        self.assertEqual(np.diff(dias).tolist(), [1] * (len(dias) - 1))
        self.assertAlmostEqual(ingresos.sum(), datos.pedido_total.sum(), places=2)


class EntrenamientoTests(BaseTiendaMl):
    def test_entrena_los_tres_modelos_y_los_guarda(self):
        omitidos = entrenar_tienda(self.tienda)
        self.assertEqual(omitidos, [])
        guardados = {m.tipo: m for m in ModeloML.objects.filter(tienda=self.tienda)}
        self.assertEqual(set(guardados), {'pronostico_ventas', 'riesgo_abandono', 'compras_conjuntas'})

        abandono_ = guardados['riesgo_abandono']
        self.assertTrue(0 <= abandono_.metricas['auc'] <= 1)
        self.assertTrue(0 <= abandono_.metricas['exactitud'] <= 1)
        self.assertLessEqual(len(abandono_.resultados['en_riesgo']), 20)
        distribucion = abandono_.resultados['distribucion']
        self.assertEqual(sum(distribucion.values()), abandono_.resultados['clientes_puntuados'])

        conjuntas = guardados['compras_conjuntas']
        par_frecuente = max(conjuntas.resultados['pares'], key=lambda f: f['pedidos'])
        self.assertEqual({par_frecuente['producto_a'], par_frecuente['producto_b']}, {'Poncho', 'Bufanda'})
        self.assertGreater(conjuntas.metricas['hit_rate_5'], 0.5)

        self.assertEqual(len(guardados['pronostico_ventas'].resultados['pronostico']['fechas']), 30)

    def test_reentrenar_es_reproducible_y_no_duplica(self):
        entrenar_tienda(self.tienda)
        primero = {m.tipo: (m.metricas, m.resultados) for m in ModeloML.objects.filter(tienda=self.tienda)}
        entrenar_tienda(self.tienda)
        segundo = {m.tipo: (m.metricas, m.resultados) for m in ModeloML.objects.filter(tienda=self.tienda)}
        self.assertEqual(primero, segundo)
        self.assertEqual(ModeloML.objects.filter(tienda=self.tienda).count(), 3)

    def test_tienda_sin_datos_omite_los_modelos_con_su_motivo(self):
        omitidos = entrenar_tienda(self.tienda_vacia)
        self.assertEqual([o['tipo'] for o in omitidos],
                         ['pronostico_ventas', 'riesgo_abandono', 'compras_conjuntas'])
        self.assertTrue(all(o['motivo'] for o in omitidos))
        self.assertEqual(ModeloML.objects.filter(tienda=self.tienda_vacia).count(), 0)

    def test_el_comando_entrena_y_valida_la_tienda(self):
        salida = StringIO()
        call_command('entrenar_modelos_ml', tienda=self.tienda.id, stdout=salida)
        self.assertEqual(ModeloML.objects.filter(tienda=self.tienda).count(), 3)
        self.assertIn('Tiempo de entrenamiento', salida.getvalue())
        with self.assertRaises(CommandError):
            call_command('entrenar_modelos_ml', tienda=999999, stdout=StringIO())


class MlApiTests(BaseTiendaMl):
    def test_sin_sesion_y_sin_permiso(self):
        self.assertEqual(self.client.get(url_ml(self.tienda.id)).status_code, 401)
        self.client.force_authenticate(self.sin_permiso)
        self.assertEqual(self.client.get(url_ml(self.tienda.id)).status_code, 403)
        self.assertEqual(self.client.post(url_entrenar(self.tienda.id)).status_code, 403)

    def test_get_sin_entrenar_devuelve_el_dataset_y_ningun_modelo(self):
        self.client.force_authenticate(self.empresa)
        res = self.client.get(url_ml(self.tienda.id))
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data['entrenado'])
        self.assertEqual(res.data['modelos'], [])
        dataset = res.data['dataset']
        self.assertEqual(dataset['pedidos'], Pedido.objects.filter(tienda=self.tienda).count())
        self.assertEqual(dataset['clientes'], 90)
        self.assertEqual(dataset['eventos'], 200)
        self.assertFalse(dataset['sintetico'])
        self.assertLessEqual(dataset['desde'], dataset['hasta'])

    def test_post_entrena_y_get_devuelve_lo_mismo(self):
        self.client.force_authenticate(self.empresa)
        res = self.client.post(url_entrenar(self.tienda.id))
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['entrenado'])
        self.assertEqual([m['tipo'] for m in res.data['modelos']],
                         ['pronostico_ventas', 'riesgo_abandono', 'compras_conjuntas'])
        for modelo in res.data['modelos']:
            self.assertEqual(
                set(modelo),
                {'tipo', 'titulo', 'algoritmo', 'entrenado_en', 'filas_entrenamiento', 'metricas',
                 'explicacion', 'resultados'})
            self.assertTrue(modelo['explicacion'])
        otra = self.client.get(url_ml(self.tienda.id))
        self.assertEqual(otra.data['modelos'], res.data['modelos'])

    def test_aislamiento_por_tienda(self):
        self.client.force_authenticate(self.otra_empresa)
        self.assertEqual(self.client.get(url_ml(self.tienda.id)).status_code, 404)
        self.assertEqual(self.client.post(url_entrenar(self.tienda.id)).status_code, 404)
        self.assertEqual(ModeloML.objects.filter(tienda=self.tienda).count(), 0)
        self.assertEqual(self.client.get(url_ml(self.tienda_ajena.id)).status_code, 200)

    def test_el_administrador_ve_cualquier_tienda(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(url_ml(self.tienda.id)).status_code, 200)

    def test_tienda_inexistente(self):
        self.client.force_authenticate(self.empresa)
        self.assertEqual(self.client.get(url_ml(999999)).status_code, 404)

    def test_tienda_sin_ventas_informa_los_motivos(self):
        self.client.force_authenticate(self.empresa)
        res = self.client.post(url_entrenar(self.tienda_vacia.id))
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data['entrenado'])
        self.assertEqual(len(res.data['omitidos']), 3)

    def test_la_matriz_de_permisos_habilita_a_otro_rol(self):
        rol = Rol.objects.get(nombre='cliente')
        RolPermiso.objects.create(rol=rol, permiso=Permiso.objects.get(codigo='informes.ver'))
        self.tienda_ajena.propietario = self.sin_permiso
        self.tienda_ajena.save()
        self.client.force_authenticate(self.sin_permiso)
        self.assertEqual(self.client.get(url_ml(self.tienda_ajena.id)).status_code, 200)
        self.assertEqual(self.client.post(url_entrenar(self.tienda_ajena.id)).status_code, 403)


class DatasetSinteticoTests(BaseTiendaMl):
    def test_sintetico_cuando_la_mayoria_de_clientes_tiene_correo_sintetico(self):
        rol = Rol.objects.get(nombre='cliente')
        usuarios = [
            Usuario.objects.create_user(email=f's{i}@sintetico.kantu.bo', password='x', rol=rol)
            for i in range(3)
        ]
        real = Usuario.objects.create_user(email='real@example.com', password='x', rol=rol)
        for usuario in usuarios + [real]:
            Pedido.objects.create(cliente=usuario, tienda=self.tienda_ajena, subtotal=0, total=0)
        self.assertTrue(carga.resumen_dataset(self.tienda_ajena)['sintetico'])
        self.assertFalse(carga.resumen_dataset(self.tienda)['sintetico'])
