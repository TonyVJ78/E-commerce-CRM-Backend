"""
Servicio de predicción de compras (CU-35, modelo C).

Estima la probabilidad de que un cliente realice al menos una compra en una
tienda dentro de un horizonte de días dado.

Diferencias clave con el motor de recomendaciones CU-14:
- CU-14 recomienda productos a un cliente navegando (filtrado por tienda actual).
- Este modelo predice si el cliente volverá a comprar en un horizonte futuro,
  usando su historial de compras y señalando la probabilidad de conversión.

Evento objetivo:
  cliente realizó al menos un pedido no cancelado en la tienda dentro de
  `horizonte_dias` días después de una fecha de corte.

Implementa una puntuación lineal simple basada en frecuencia, recencia,
monetario y regularidad, transformada con sigmoid. No usa librerías externas.
"""

from collections import defaultdict
from datetime import timedelta
import math

from django.utils import timezone

from apps.pedidos.models import ItemPedido, Pedido


def _sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    return math.exp(z) / (1.0 + math.exp(z))


def _normalizar(valor, vmin, vmax):
    if vmax == vmin:
        return 0.5
    return (valor - vmin) / (vmax - vmin)


def _metricas_clasificacion(y_true, y_pred, probs=None):
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    n = len(y_true)
    accuracy = (tp + tn) / n if n else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    brier = None
    if probs is not None and n:
        brier = round(sum((p - t) ** 2 for p, t in zip(probs, y_true)) / n, 4)
    return {
        'accuracy': round(accuracy, 4),
        'precision': round(precision, 4),
        'recall': round(recall, 4),
        'f1': round(f1, 4),
        'matriz_confusion': {'tp': tp, 'tn': tn, 'fp': fp, 'fn': fn},
        'brier_score': brier,
    }


def predecir_compra(tienda, cliente_id, horizonte_dias=7):
    """
    Predice la probabilidad de próxima compra de un cliente en una tienda.

    Retorna dict con:
      - tienda_id, tienda_nombre, cliente_id, horizonte_dias
      - fecha_corte (última fecha de pedido considerada)
      - estado: 'completado' o 'datos_insuficientes'
      - probabilidad_compra (float 0-1) o None
      - nivel (bajo/medio/alto)
      - variables_explicativas
      - metrica: evaluación simple si hay suficientes datos
    """
    hoy = timezone.now().date()

    pedidos = (
        Pedido.objects.filter(tienda=tienda)
        .exclude(estado_actual__iexact='cancelado')
        .select_related('cliente')
        .order_by('fecha')
    )

    if not pedidos:
        return {
            'tienda_id': tienda.id,
            'tienda_nombre': tienda.nombre,
            'cliente_id': cliente_id,
            'horizonte_dias': horizonte_dias,
            'fecha_corte': str(hoy),
            'estado': 'datos_insuficientes',
            'mensaje': 'No hay pedidos válidos en esta tienda.',
            'probabilidad_compra': None,
            'nivel': 'desconocido',
            'variables_explicativas': {},
            'metrica': None,
        }

    fecha_referencia = max(p.fecha.date() for p in pedidos)

    # Agrupar pedidos por cliente
    por_cliente = defaultdict(list)
    for p in pedidos:
        if p.cliente_id is None:
            continue
        por_cliente[p.cliente_id].append(p)

    # Verificar si el cliente solicitado existe en la tienda
    if cliente_id not in por_cliente:
        # Cliente sin historial en esta tienda: probabilidad base muy baja
        return {
            'tienda_id': tienda.id,
            'tienda_nombre': tienda.nombre,
            'cliente_id': cliente_id,
            'horizonte_dias': horizonte_dias,
            'fecha_corte': str(fecha_referencia),
            'estado': 'datos_insuficientes',
            'mensaje': (
                f'El cliente {cliente_id} no tiene historial de compras en '
                f'esta tienda.'
            ),
            'probabilidad_compra': 0.05,
            'nivel': 'bajo',
            'variables_explicativas': {
                'tiene_historial': False,
                'frecuencia': 0,
                'recencia_dias': None,
                'monetario_total': 0.0,
            },
            'metrica': None,
        }

    # Construir dataset para entrenamiento (todas las tiendas de referencia)
    # Para cada cliente, definimos una fecha de corte pasada y miramos si compró
    # dentro del horizonte después de esa corte.
    registros = []
    for cid, ps in por_cliente.items():
        fechas = sorted(p.fecha.date() for p in ps)
        ultima = fechas[-1]
        primera = fechas[0]
        recencia = (fecha_referencia - ultima).days
        frecuencia = len(ps)
        monetario = sum(float(p.total) for p in ps)
        dias_cliente = max((fecha_referencia - primera).days, 1)
        promedio_intervalo = (
            (ultima - primera).days / max(frecuencia - 1, 1) if frecuencia > 1 else 0
        )

        # Etiqueta: ¿compró en los `horizonte_dias` después de la penúltima fecha?
        # Usamos la fecha de corte = fecha_referencia - horizonte_dias, y miramos
        # si hay pedidos entre corte y fecha_referencia.
        fecha_corte_etiqueta = fecha_referencia - timedelta(days=horizonte_dias)
        compro_después_corte = any(
            fecha_corte_etiqueta < f <= fecha_referencia for f in fechas
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
        # Datos insuficientes para entrenar, pero devolvemos heurística para el cliente solicitado
        r = [x for x in registros if x['cliente_id'] == cliente_id][0]
        probabilidad = _heuristica_probabilidad(
            r['recencia'], r['frecuencia'], r['monetario'], r['dias_cliente']
        )
        return {
            'tienda_id': tienda.id,
            'tienda_nombre': tienda.nombre,
            'cliente_id': cliente_id,
            'horizonte_dias': horizonte_dias,
            'fecha_corte': str(fecha_referencia),
            'estado': 'datos_insuficientes',
            'mensaje': (
                f'Solo {len(registros)} cliente(s) con historial; se requieren '
                f'al menos 5 para entrenar el modelo.'
            ),
            'probabilidad_compra': round(probabilidad, 4),
            'nivel': _nivel(probabilidad),
            'variables_explicativas': {
                'tiene_historial': True,
                'frecuencia': r['frecuencia'],
                'recencia_dias': r['recencia'],
                'monetario_total': round(r['monetario'], 2),
                'dias_cliente': r['dias_cliente'],
            },
            'metrica': None,
        }

    # Features y etiquetas
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

    # Entrenamiento: puntuación lineal ponderada (regresión logística simple)
    # Pesos heurísticos iniciales ajustados por gradiente descendente reducido.
    pesos = [0.4, 0.3, 0.2, -0.2]  # recencia(negativa), frecuencia, monetario, intervalo
    sesgo = -0.5

    n = len(X)
    corte = max(int(n * 0.8), 2)
    X_train, y_train = X[:corte], y[:corte]
    X_test, y_test = X[corte:], y[corte:]

    # Un par de épocas de ajuste ligero (no es entrenamiento pesado)
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

    # Predicción para el cliente solicitado
    r_solicitado = [x for x in registros if x['cliente_id'] == cliente_id][0]
    x_cliente = [
        _normalizar(r_solicitado['recencia'], min(recs), max(recs)),
        _normalizar(r_solicitado['frecuencia'], min(frecs), max(frecs)),
        _normalizar(r_solicitado['monetario'], min(mons), max(mons)),
        _normalizar(r_solicitado['promedio_intervalo'], min(ints), max(ints)),
    ]
    probabilidad = _sigmoid(sesgo + sum(p * w for p, w in zip(x_cliente, pesos)))

    # Métrica en prueba con umbral 0.5
    metrica = None
    if X_test:
        probs_test = [_sigmoid(sesgo + sum(p * w for p, w in zip(xt, pesos))) for xt in X_test]
        y_pred_test = [1 if p >= 0.5 else 0 for p in probs_test]
        metrica = _metricas_clasificacion(y_test, y_pred_test, probs_test)
        metrica['clientes_entrenados'] = len(X_train)
        metrica['clientes_prueba'] = len(y_test)
        metrica['compra_en_entrenamiento'] = sum(y_train)
        metrica['compra_en_prueba'] = sum(y_test)
        metrica['metodo'] = 'puntuación lineal + sigmoid (holdout temporal)'

        # Baseline de clase mayoritaria
        clase_may = 1 if sum(y_train) > len(y_train) / 2 else 0
        y_pred_base = [clase_may] * len(y_test)
        metrica['baseline_clase_mayoritaria'] = _metricas_clasificacion(y_test, y_pred_base)

    return {
        'tienda_id': tienda.id,
        'tienda_nombre': tienda.nombre,
        'cliente_id': cliente_id,
        'horizonte_dias': horizonte_dias,
        'fecha_corte': str(fecha_referencia),
        'estado': 'completado',
        'mensaje': 'Predicción de compra generada con puntuación lineal simple.',
        'probabilidad_compra': round(probabilidad, 4),
        'nivel': _nivel(probabilidad),
        'variables_explicativas': {
            'tiene_historial': True,
            'frecuencia': r_solicitado['frecuencia'],
            'recencia_dias': r_solicitado['recencia'],
            'monetario_total': round(r_solicitado['monetario'], 2),
            'promedio_intervalo_dias': round(r_solicitado['promedio_intervalo'], 2),
            'dias_cliente': r_solicitado['dias_cliente'],
        },
        'metrica': metrica,
    }


def _heuristica_probabilidad(recencia, frecuencia, monetario, dias_cliente):
    """Probabilidad base cuando no hay datos para entrenar."""
    score = 0.0
    if recencia <= 7:
        score += 0.4
    elif recencia <= 30:
        score += 0.2
    if frecuencia >= 5:
        score += 0.3
    elif frecuencia >= 2:
        score += 0.15
    if monetario > 0:
        score += 0.2
    return min(max(score, 0.0), 1.0)


def _nivel(prob):
    if prob < 0.4:
        return 'bajo'
    if prob < 0.7:
        return 'medio'
    return 'alto'
