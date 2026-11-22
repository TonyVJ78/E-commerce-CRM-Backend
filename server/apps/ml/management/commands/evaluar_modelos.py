"""
Comando permanente de evaluación offline de CU-35.

Genera datos sintéticos reproducibles (seed=42) y evalúa los tres modelos de
Machine Learning sin tocar Neon ni tablas comerciales de producción.

Uso:
    python manage.py evaluar_modelos --seed 42 --clientes 1000 --tiendas 5 --salida metriques.json

Todas las métricas se calculan sobre datos sintéticos en memoria.
"""

import json
import math
import os
from datetime import date, timedelta
from collections import defaultdict

from django.core.management.base import BaseCommand

from apps.ml.services.sinteticos import generar_datos_sinteticos


def _sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    return math.exp(z) / (1.0 + math.exp(z))


def _normalizar(valor, vmin, vmax):
    if vmax == vmin:
        return 0.5
    return (valor - vmin) / (vmax - vmin)


def _regresion_lineal_simple(x_vals, y_vals):
    n = len(x_vals)
    if n == 0:
        return 0.0, 0.0
    sx = sum(x_vals)
    sy = sum(y_vals)
    sxx = sum(x * x for x in x_vals)
    sxy = sum(x * y for x, y in zip(x_vals, y_vals))
    denom = n * sxx - sx * sx
    if denom == 0:
        return sy / n, 0.0
    b = (n * sxy - sx * sy) / denom
    a = (sy - b * sx) / n
    return a, b


def _mae_rmse(y_true, y_pred):
    n = len(y_true)
    if n == 0:
        return None, None
    mae = sum(abs(t - p) for t, p in zip(y_true, y_pred)) / n
    rmse = (sum((t - p) ** 2 for t, p in zip(y_true, y_pred)) / n) ** 0.5
    return round(mae, 4), round(rmse, 4)


def _entrenar_regresion_logistica(X, y, tasa_aprendizaje=0.1, epocas=2000):
    n = len(X)
    k = len(X[0]) if n else 0
    pesos = [0.0] * k
    sesgo = 0.0
    for _ in range(epocas):
        grad_pesos = [0.0] * k
        grad_sesgo = 0.0
        for i in range(n):
            z = sesgo + sum(pesos[j] * X[i][j] for j in range(k))
            p = _sigmoid(z)
            error = p - y[i]
            grad_sesgo += error
            for j in range(k):
                grad_pesos[j] += error * X[i][j]
        for j in range(k):
            pesos[j] -= (tasa_aprendizaje / n) * grad_pesos[j]
        sesgo -= (tasa_aprendizaje / n) * grad_sesgo
    return pesos, sesgo


def _predecir_logistica(X, pesos, sesgo):
    return [_sigmoid(sesgo + sum(p * w for p, w in zip(x, pesos))) for x in X]


def metricas_clasificacion(y_true, y_pred):
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    accuracy = (tp + tn) / len(y_true) if y_true else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    return {
        'accuracy': round(accuracy, 4),
        'precision': round(precision, 4),
        'recall': round(recall, 4),
        'f1': round(f1, 4),
        'matriz_confusion': {'tp': tp, 'tn': tn, 'fp': fp, 'fn': fn},
    }


def brier_score(y_true, probs):
    n = len(y_true)
    if n == 0:
        return None
    return round(sum((p - t) ** 2 for p, t in zip(probs, y_true)) / n, 4)


def _brier_clasificacion(y_true, probs, umbral=0.5):
    y_pred = [1 if p >= umbral else 0 for p in probs]
    return metricas_clasificacion(y_true, y_pred), brier_score(y_true, probs)


# =====================================================================
# MODELO A: Pronóstico de ventas (sobre estructuras sintéticas)
# =====================================================================

def evaluar_ventas(datos, tienda_id, horizonte_dias=7):
    pedidos = [
        p for p in datos['pedidos']
        if p['tienda_id'] == tienda_id and p['estado_actual'] != 'cancelado'
    ]
    if not pedidos:
        return {'estado': 'datos_insuficientes'}

    ingresos_por_dia = defaultdict(float)
    for p in pedidos:
        d = date.fromisoformat(p['fecha'])
        ingresos_por_dia[d] += float(p['total'])

    fecha_inicio = min(ingresos_por_dia.keys())
    fecha_fin = max(ingresos_por_dia.keys())
    fecha_corte = fecha_fin

    serie = []
    actual = fecha_inicio
    while actual <= fecha_fin:
        serie.append((actual, ingresos_por_dia.get(actual, 0.0)))
        actual += timedelta(days=1)

    if len(serie) < 7:
        return {'estado': 'datos_insuficientes'}

    datos_train = [(i, v) for i, (f, v) in enumerate(serie) if f <= fecha_corte]
    x_train = [d for d, _ in datos_train]
    y_train = [v for _, v in datos_train]
    a, b = _regresion_lineal_simple(x_train, y_train)

    metrica = None
    n_total = len(datos_train)
    if n_total >= 14:
        corte_holdout = int(n_total * 0.8)
        x_test = x_train[corte_holdout:]
        y_test = y_train[corte_holdout:]
        y_pred = [a + b * x for x in x_test]
        mae, rmse = _mae_rmse(y_test, y_pred)

        # Baseline ingenuo: valor medio de entrenamiento
        valor_medio = sum(y_train[:corte_holdout]) / corte_holdout
        y_pred_base = [valor_medio] * len(x_test)
        base_mae, base_rmse = _mae_rmse(y_test, y_pred_base)

        metrica = {
            'mae': mae,
            'rmse': rmse,
            'datos_entrenamiento': corte_holdout,
            'datos_prueba': len(x_test),
            'baseline_mae': base_mae,
            'baseline_rmse': base_rmse,
            'metodo': 'regresión lineal simple (holdout temporal)',
        }

    indice_ultimo = x_train[-1]
    fechas_previstas = []
    for paso in range(1, horizonte_dias + 1):
        fecha_pred = fecha_corte + timedelta(days=paso)
        x_pred = indice_ultimo + paso
        valor = max(0.0, a + b * x_pred)
        fechas_previstas.append({'fecha': str(fecha_pred), 'valor_previsto': round(valor, 2)})

    return {
        'estado': 'completado',
        'tienda_id': tienda_id,
        'horizonte_dias': horizonte_dias,
        'fecha_corte': str(fecha_corte),
        'fechas_previstas': fechas_previstas,
        'metrica': metrica,
        'coeficientes': {'intercepto': round(a, 4), 'pendiente': round(b, 6)},
    }


# =====================================================================
# MODELO B: Riesgo de abandono (sin fuga temporal)
# =====================================================================

def evaluar_abandono(datos, tienda_id, dias_umbral_abandono=90):
    """
    Define abandono con fecha de corte y período de observación posterior.

    Fecha de corte: última compra registrada en la tienda.
    Etiqueta: abandono=1 si la última compra del cliente ocurrió hace más de
    `dias_umbral_abandono` días ANTES de la fecha de corte.
    Predictores: solo información anterior o igual al corte (recencia,
    frecuencia, monetario, días como cliente). No se usa información futura.
    """
    fecha_corte = max(date.fromisoformat(p['fecha']) for p in datos['pedidos']
                      if p['tienda_id'] == tienda_id)

    pedidos = [
        p for p in datos['pedidos']
        if p['tienda_id'] == tienda_id and p['estado_actual'] != 'cancelado'
    ]
    if not pedidos:
        return {'estado': 'datos_insuficientes'}

    por_cliente = defaultdict(list)
    for p in pedidos:
        if p['cliente_id'] is None:
            continue
        por_cliente[p['cliente_id']].append(p)

    registros = []
    for cid, ps in por_cliente.items():
        if len(ps) < 1:
            continue
        fechas = sorted(date.fromisoformat(p['fecha']) for p in ps)
        ultima = fechas[-1]
        primera = fechas[0]
        recencia = (fecha_corte - ultima).days
        frecuencia = len(ps)
        monetario = sum(float(p['total']) for p in ps)
        dias_cliente = max((fecha_corte - primera).days, 1)

        # Etiqueta de abandono: última compra antes del corte, más allá del umbral
        abandonado = 1 if recencia > dias_umbral_abandono else 0

        registros.append({
            'cliente_id': cid,
            'recencia': recencia,
            'frecuencia': frecuencia,
            'monetario': monetario,
            'dias_cliente': dias_cliente,
            'abandono': abandonado,
        })

    if len(registros) < 5:
        return {'estado': 'datos_insuficientes', 'clientes_evaluados': len(registros)}

    abandonados = sum(r['abandono'] for r in registros)
    if abandonados < 2:
        return {'estado': 'datos_insuficientes',
                'mensaje': f'Solo {abandonados} abandono(s) etiquetado(s); se requieren >= 2.',
                'clientes_evaluados': len(registros)}

    recs = [r['recencia'] for r in registros]
    frecs = [r['frecuencia'] for r in registros]
    mons = [r['monetario'] for r in registros]

    X = []
    y = []
    for r in registros:
        X.append([
            _normalizar(r['recencia'], min(recs), max(recs)),
            _normalizar(r['frecuencia'], min(frecs), max(frecs)),
            _normalizar(r['monetario'], min(mons), max(mons)),
            _normalizar(r['dias_cliente'], 1, max(r['dias_cliente'] for r in registros)),
        ])
        y.append(r['abandono'])

    n = len(X)
    corte = max(int(n * 0.8), 2)
    X_train, y_train = X[:corte], y[:corte]
    X_test, y_test = X[corte:], y[corte:]

    pesos, sesgo = _entrenar_regresion_logistica(X_train, y_train)
    probs_test = _predecir_logistica(X_test, pesos, sesgo)
    y_pred_test = [1 if p >= 0.5 else 0 for p in probs_test]

    metrica, brier = _brier_clasificacion(y_test, probs_test)
    metrica['clientes_entrenados'] = len(X_train)
    metrica['clientes_prueba'] = len(X_test)
    metrica['abandono_en_entrenamiento'] = sum(y_train)
    metrica['abandono_en_prueba'] = sum(y_test)
    metrica['brier_score'] = brier
    metrica['metodo'] = 'regresión logística simple (holdout temporal, sin fuga)'

    # Baseline de clase mayoritaria
    clase_may = 1 if sum(y_train) > len(y_train) / 2 else 0
    y_pred_base = [clase_may] * len(y_test)
    metrica_base = metricas_clasificacion(y_test, y_pred_base)

    # Distribución de probabilidades
    probs_rango = {'0.0-0.2': 0, '0.2-0.4': 0, '0.4-0.6': 0, '0.6-0.8': 0, '0.8-1.0': 0}
    probs_todos = _predecir_logistica(X, pesos, sesgo)
    for p in probs_todos:
        if p < 0.2:
            probs_rango['0.0-0.2'] += 1
        elif p < 0.4:
            probs_rango['0.2-0.4'] += 1
        elif p < 0.6:
            probs_rango['0.4-0.6'] += 1
        elif p < 0.8:
            probs_rango['0.6-0.8'] += 1
        else:
            probs_rango['0.8-1.0'] += 1

    resultados = []
    for r, prob in zip(registros, probs_todos):
        resultados.append({
            'cliente_id': r['cliente_id'],
            'probabilidad_abandono': round(prob, 4),
            'nivel_riesgo': 'critico' if prob >= 0.85 else ('alto' if prob >= 0.66 else ('medio' if prob >= 0.33 else 'bajo')),
            'recencia_dias': r['recencia'],
            'frecuencia': r['frecuencia'],
            'monetario_total': round(r['monetario'], 2),
            'abandono_real': bool(r['abandono']),
        })
    resultados.sort(key=lambda x: -x['probabilidad_abandono'])

    return {
        'estado': 'completado',
        'tienda_id': tienda_id,
        'fecha_corte': str(fecha_corte),
        'dias_umbral_abandono': dias_umbral_abandono,
        'clientes_evaluados': len(registros),
        'metrica': metrica,
        'baseline_clase_mayoritaria': metrica_base,
        'distribucion_probabilidades': probs_rango,
        'ejemplos_prediccion': resultados[:5],
    }


# =====================================================================
# MODELO C: Predicción de compras (horizontes 7 y 30 días)
# =====================================================================

def evaluar_compras(datos, tienda_id, cliente_id, horizonte_dias=7):
    fecha_corte = max(date.fromisoformat(p['fecha']) for p in datos['pedidos']
                      if p['tienda_id'] == tienda_id)

    pedidos = [
        p for p in datos['pedidos']
        if p['tienda_id'] == tienda_id and p['estado_actual'] != 'cancelado'
    ]
    if not pedidos:
        return {'estado': 'datos_insuficientes'}

    por_cliente = defaultdict(list)
    for p in pedidos:
        if p['cliente_id'] is None:
            continue
        por_cliente[p['cliente_id']].append(p)

    if cliente_id not in por_cliente:
        return {
            'estado': 'datos_insuficientes',
            'mensaje': f'Cliente {cliente_id} sin historial en tienda {tienda_id}',
            'probabilidad_compra': 0.05,
        }

    registros = []
    for cid, ps in por_cliente.items():
        fechas = sorted(date.fromisoformat(p['fecha']) for p in ps)
        ultima = fechas[-1]
        primera = fechas[0]
        recencia = (fecha_corte - ultima).days
        frecuencia = len(ps)
        monetario = sum(float(p['total']) for p in ps)
        dias_cliente = max((fecha_corte - primera).days, 1)
        promedio_intervalo = (
            (ultima - primera).days / max(frecuencia - 1, 1) if frecuencia > 1 else 0
        )

        # Etiqueta: compró dentro del horizonte después del corte
        fecha_corte_etiqueta = fecha_corte - timedelta(days=horizonte_dias)
        compro_después_corte = any(
            fecha_corte_etiqueta < f <= fecha_corte for f in fechas
        )

        registros.append({
            'cliente_id': cid,
            'recencia': recencia,
            'frecuencia': frecuencia,
            'monetario': monetario,
            'dias_cliente': dias_cliente,
            'promedio_intervalo': promedio_intervalo,
            'compro_en_horizonte': 1 if compro_después_corte else 0,
        })

    if len(registros) < 5:
        return {'estado': 'datos_insuficientes', 'clientes_evaluados': len(registros)}

    recs = [r['recencia'] for r in registros]
    frecs = [r['frecuencia'] for r in registros]
    mons = [r['monetario'] for r in registros]
    ints = [r['promedio_intervalo'] for r in registros]

    X = []
    y = []
    for r in registros:
        X.append([
            _normalizar(r['recencia'], min(recs), max(recs)),
            _normalizar(r['frecuencia'], min(frecs), max(frecs)),
            _normalizar(r['monetario'], min(mons), max(mons)),
            _normalizar(r['promedio_intervalo'], min(ints), max(ints)),
        ])
        y.append(r['compro_en_horizonte'])

    pesos = [0.4, 0.3, 0.2, -0.2]
    sesgo = -0.5
    n = len(X)
    corte = max(int(n * 0.8), 2)
    X_train, y_train = X[:corte], y[:corte]
    X_test, y_test = X[corte:], y[corte:]

    tasa = 0.05
    for _ in range(500):
        grad_w = [0.0] * 4
        grad_b = 0.0
        for i in range(len(X_train)):
            z = sesgo + sum(p * w for p, w in zip(X_train[i], pesos))
            p = _sigmoid(z)
            error = p - y_train[i]
            grad_b += error
            for j in range(4):
                grad_w[j] += error * X_train[i][j]
        for j in range(4):
            pesos[j] -= (tasa / len(X_train)) * grad_w[j]
        sesgo -= (tasa / len(X_train)) * grad_b

    probs_test = _predecir_logistica(X_test, pesos, sesgo)
    y_pred_test = [1 if p >= 0.5 else 0 for p in probs_test]

    metrica, brier = _brier_clasificacion(y_test, probs_test)
    metrica['clientes_entrenados'] = len(X_train)
    metrica['clientes_prueba'] = len(X_test)
    metrica['compra_en_entrenamiento'] = sum(y_train)
    metrica['compra_en_prueba'] = sum(y_test)
    metrica['brier_score'] = brier
    metrica['metodo'] = 'puntuación lineal + sigmoid (holdout temporal)'

    clase_may = 1 if sum(y_train) > len(y_train) / 2 else 0
    y_pred_base = [clase_may] * len(y_test)
    metrica_base = metricas_clasificacion(y_test, y_pred_base)

    r_solicitado = [x for x in registros if x['cliente_id'] == cliente_id][0]
    x_cliente = [
        _normalizar(r_solicitado['recencia'], min(recs), max(recs)),
        _normalizar(r_solicitado['frecuencia'], min(frecs), max(frecs)),
        _normalizar(r_solicitado['monetario'], min(mons), max(mons)),
        _normalizar(r_solicitado['promedio_intervalo'], min(ints), max(ints)),
    ]
    probabilidad = _sigmoid(sesgo + sum(p * w for p, w in zip(x_cliente, pesos)))

    return {
        'estado': 'completado',
        'tienda_id': tienda_id,
        'cliente_id': cliente_id,
        'horizonte_dias': horizonte_dias,
        'fecha_corte': str(fecha_corte),
        'probabilidad_compra': round(probabilidad, 4),
        'nivel': 'alto' if probabilidad >= 0.7 else ('medio' if probabilidad >= 0.4 else 'bajo'),
        'metrica': metrica,
        'baseline_clase_mayoritaria': metrica_base,
        'variables_explicativas': {
            'tiene_historial': True,
            'frecuencia': r_solicitado['frecuencia'],
            'recencia_dias': r_solicitado['recencia'],
            'monetario_total': round(r_solicitado['monetario'], 2),
            'promedio_intervalo_dias': round(r_solicitado['promedio_intervalo'], 2),
            'dias_cliente': r_solicitado['dias_cliente'],
        },
    }


# =====================================================================
# Comando Django
# =====================================================================

class Command(BaseCommand):
    help = 'Evalúa offline los modelos de ML de CU-35 con datos sintéticos.'

    def add_arguments(self, parser):
        parser.add_argument('--seed', type=int, default=42, help='Semilla aleatoria')
        parser.add_argument('--clientes', type=int, default=1000, help='Número de clientes')
        parser.add_argument('--tiendas', type=int, default=5, help='Número de tiendas')
        parser.add_argument(
            '--salida',
            type=str,
            default=None,
            help='Ruta del archivo JSON donde guardar métricas (opcional)',
        )

    def handle(self, *args, **options):
        seed = options['seed']
        n_clientes = options['clientes']
        n_tiendas = options['tiendas']
        salida = options['salida']

        self.stdout.write(self.style.NOTICE(
            f'Generando datos sintéticos (seed={seed}, clientes={n_clientes}, tiendas={n_tiendas})...'
        ))
        datos = generar_datos_sinteticos(seed=seed, n_clientes=n_clientes, n_tiendas=n_tiendas)
        res = datos['resumen']

        self.stdout.write(f'Clientes: {res["n_clientes"]}')
        self.stdout.write(f'Pedidos: {res["n_pedidos"]}')
        self.stdout.write(f'Patrones: {res["distribucion_patrones"]}')
        self.stdout.write(f'Abandonos etiquetados: {res["n_clientes_abandono_etiquetado"]}')

        reporte = {
            'semilla': seed,
            'datos_sinteticos': True,
            'n_clientes': res['n_clientes'],
            'n_pedidos': res['n_pedidos'],
            'distribucion_patrones': res['distribucion_patrones'],
            'distribucion_estados': res['distribucion_estados_pedidos'],
            'tiendas': [],
        }

        for tienda in datos['tiendas']:
            tid = tienda['id']
            self.stdout.write(self.style.NOTICE(f'\n--- Tienda {tid}: {tienda["nombre"]} ---'))

            r_ventas = evaluar_ventas(datos, tid, horizonte_dias=7)
            r_abandono = evaluar_abandono(datos, tid, dias_umbral_abandono=90)

            clientes_tienda = [c for c in datos['clientes'] if c['tienda_id'] == tid and
                              any(p['cliente_id'] == c['id'] and p['estado_actual'] != 'cancelado'
                                  for p in datos['pedidos'])]
            cliente_ejemplo = clientes_tienda[0] if clientes_tienda else None

            r_compra_7 = None
            r_compra_30 = None
            if cliente_ejemplo:
                r_compra_7 = evaluar_compras(datos, tid, cliente_ejemplo['id'], horizonte_dias=7)
                r_compra_30 = evaluar_compras(datos, tid, cliente_ejemplo['id'], horizonte_dias=30)

            tienda_reporte = {
                'tienda_id': tid,
                'nombre': tienda['nombre'],
                'ventas': r_ventas,
                'abandono': r_abandono,
                'compras_7d': r_compra_7,
                'compras_30d': r_compra_30,
                'cliente_ejemplo_email': cliente_ejemplo['email'] if cliente_ejemplo else None,
            }
            reporte['tiendas'].append(tienda_reporte)

            self._imprimir_resumen_tienda(tienda_reporte)

        if salida:
            with open(salida, 'w', encoding='utf-8') as f:
                json.dump(reporte, f, indent=2, ensure_ascii=False, default=str)
            self.stdout.write(self.style.SUCCESS(f'\nMétricas guardadas en: {salida}'))
        else:
            self.stdout.write(self.style.WARNING(
                '\nNo se especificó --salida; las métricas solo se mostraron por consola.'
            ))

        self.stdout.write(self.style.SUCCESS('\nEvaluación CU-35 completada (datos sintéticos).'))

    def _imprimir_resumen_tienda(self, t):
        # Ventas
        v = t['ventas']
        if v.get('estado') == 'completado' and v.get('metrica'):
            m = v['metrica']
            self.stdout.write(
                f'  [Ventas] MAE={m["mae"]} RMSE={m["rmse"]} | '
                f'Baseline MAE={m["baseline_mae"]} | '
                f'Entrenamiento={m["datos_entrenamiento"]} Prueba={m["datos_prueba"]}'
            )
        else:
            self.stdout.write(f'  [Ventas] {v.get("estado", "desconocido")}')

        # Abandono
        a = t['abandono']
        if a.get('estado') == 'completado' and a.get('metrica'):
            m = a['metrica']
            b = a['baseline_clase_mayoritaria']
            self.stdout.write(
                f'  [Abandono] Acc={m["accuracy"]} Prec={m["precision"]} '
                f'Rec={m["recall"]} F1={m["f1"]} Brier={m.get("brier_score")} | '
                f'Baseline Acc={b["accuracy"]} | '
                f'Entrenamiento={m["clientes_entrenados"]} Prueba={m["clientes_prueba"]}'
            )
        else:
            self.stdout.write(f'  [Abandono] {a.get("estado", "desconocido")}')

        # Compras 7d
        c7 = t.get('compras_7d')
        if c7 and c7.get('estado') == 'completado' and c7.get('metrica'):
            m = c7['metrica']
            b = c7['baseline_clase_mayoritaria']
            self.stdout.write(
                f'  [Compras 7d] Prob={c7["probabilidad_compra"]} Nivel={c7["nivel"]} | '
                f'Acc={m["accuracy"]} Prec={m["precision"]} Rec={m["recall"]} F1={m["f1"]} | '
                f'Baseline Acc={b["accuracy"]}'
            )
        elif c7:
            self.stdout.write(f'  [Compras 7d] {c7.get("estado", "desconocido")}')

        # Compras 30d
        c30 = t.get('compras_30d')
        if c30 and c30.get('estado') == 'completado' and c30.get('metrica'):
            m = c30['metrica']
            b = c30['baseline_clase_mayoritaria']
            self.stdout.write(
                f'  [Compras 30d] Prob={c30["probabilidad_compra"]} Nivel={c30["nivel"]} | '
                f'Acc={m["accuracy"]} Prec={m["precision"]} Rec={m["recall"]} F1={m["f1"]} | '
                f'Baseline Acc={b["accuracy"]}'
            )
        elif c30:
            self.stdout.write(f'  [Compras 30d] {c30.get("estado", "desconocido")}')
