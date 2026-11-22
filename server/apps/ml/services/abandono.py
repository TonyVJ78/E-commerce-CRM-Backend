"""
Servicio de riesgo de abandono de clientes (CU-35, modelo B).

Implementa un clasificador ligero basado en señales RFM (recencia, frecuencia,
valor monetario) sobre pedidos reales de la tienda. Usa solo la biblioteca
estándar de Python.

Definición verificable de abandono:
  Un cliente se considera "abandono=1" si tiene al menos un pedido no cancelado
  en la tienda y su última compra ocurrió hace más de `dias_umbral_abandono`
  días respecto a la fecha de compra más reciente registrada en la tienda.

Entrenamiento:
  Regresión logística simple implementada a mano (gradiente descendente) sobre
  features normalizados. Solo se entrena si existen suficientes datos
  etiquetados (>= 5 clientes con historial y >= 2 abandonados).

Salida:
  Lista de clientes con probabilidad estimada, nivel de riesgo y variables
  explicativas. Si hay datos insuficientes, se devuelve estado
  'datos_insuficientes' sin inventar probabilidades.
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


def _entrenar_regresion_logistica(X, y, tasa_aprendizaje=0.1, epocas=2000):
    """Entrena una regresión logística simple con gradiente descendente."""
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


def _nivel_riesgo(prob):
    if prob < 0.33:
        return 'bajo'
    if prob < 0.66:
        return 'medio'
    if prob < 0.85:
        return 'alto'
    return 'critico'


def _metricas_clasificacion(y_true, y_pred, probs=None):
    """Calcula accuracy, precision, recall, f1, matriz de confusión y Brier."""
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


def evaluar_riesgo_abandono(tienda, dias_umbral_abandono=90):
    """
    Evalúa el riesgo de abandono de los clientes de una tienda.

    Retorna dict con:
      - tienda_id, tienda_nombre
      - dias_umbral_abandono
      - fecha_referencia (fecha de compra más reciente en la tienda)
      - estado: 'completado' o 'datos_insuficientes'
      - clientes: lista de {cliente_id, email, probabilidad_abandono,
        nivel_riesgo, recencia_dias, frecuencia, monetario_total,
        variables_explicativas}
      - metrica: {accuracy, clientes_entrenados, abandonados} o None
    """
    hoy = timezone.now().date()

    # Pedidos no cancelados de la tienda
    pedidos = (
        Pedido.objects.filter(tienda=tienda)
        .exclude(estado_actual__iexact='cancelado')
        .select_related('cliente')
        .order_by('cliente_id', 'fecha')
    )

    if not pedidos:
        return {
            'tienda_id': tienda.id,
            'tienda_nombre': tienda.nombre,
            'dias_umbral_abandono': dias_umbral_abandono,
            'fecha_referencia': str(hoy),
            'estado': 'datos_insuficientes',
            'mensaje': 'No hay pedidos válidos en esta tienda.',
            'clientes': [],
            'metrica': None,
        }

    # Fecha de referencia: última compra registrada en la tienda
    fecha_referencia = max(p.fecha.date() for p in pedidos)

    # Agrupar por cliente
    por_cliente = defaultdict(list)
    for p in pedidos:
        if p.cliente_id is None:
            continue
        por_cliente[p.cliente_id].append(p)

    clientes_con_historial = [
        (cid, ps) for cid, ps in por_cliente.items() if len(ps) >= 1
    ]
    if len(clientes_con_historial) < 5:
        return {
            'tienda_id': tienda.id,
            'tienda_nombre': tienda.nombre,
            'dias_umbral_abandono': dias_umbral_abandono,
            'fecha_referencia': str(fecha_referencia),
            'estado': 'datos_insuficientes',
            'mensaje': (
                f'Solo {len(clientes_con_historial)} cliente(s) con historial; '
                f'se requieren al menos 5.'
            ),
            'clientes': [],
            'metrica': None,
        }

    # Construir features y etiquetas
    registros = []
    for cid, ps in clientes_con_historial:
        fechas = [p.fecha.date() for p in ps]
        ultima = max(fechas)
        primera = min(fechas)
        recencia = (fecha_referencia - ultima).days
        frecuencia = len(ps)
        monetario = sum(float(p.total) for p in ps)
        dias_cliente = max((fecha_referencia - primera).days, 1)
        promedio = monetario / frecuencia

        abandonado = 1 if recencia > dias_umbral_abandono else 0

        registros.append({
            'cliente_id': cid,
            'email': ps[0].cliente.email if ps[0].cliente else '',
            'recencia': recencia,
            'frecuencia': frecuencia,
            'monetario': monetario,
            'dias_cliente': dias_cliente,
            'promedio': promedio,
            'abandono': abandonado,
        })

    abandonados = sum(r['abandono'] for r in registros)
    if abandonados < 2:
        return {
            'tienda_id': tienda.id,
            'tienda_nombre': tienda.nombre,
            'dias_umbral_abandono': dias_umbral_abandono,
            'fecha_referencia': str(fecha_referencia),
            'estado': 'datos_insuficientes',
            'mensaje': (
                f'Solo {abandonados} cliente(s) etiquetado(s) como abandono; '
                f'se requieren al menos 2.'
            ),
            'clientes': [],
            'metrica': None,
        }

    # Normalizar features (min-max)
    def normalizar(valor, vmin, vmax):
        if vmax == vmin:
            return 0.5
        return (valor - vmin) / (vmax - vmin)

    recs = [r['recencia'] for r in registros]
    frecs = [r['frecuencia'] for r in registros]
    mons = [r['monetario'] for r in registros]

    X = []
    y = []
    for r in registros:
        X.append([
            normalizar(r['recencia'], min(recs), max(recs)),
            normalizar(r['frecuencia'], min(frecs), max(frecs)),
            normalizar(r['monetario'], min(mons), max(mons)),
            normalizar(r['dias_cliente'], 1, max(r['dias_cliente'] for r in registros)),
        ])
        y.append(r['abandono'])

    # Entrenar con todos los datos (holdout temporal simple si hay suficientes)
    n = len(X)
    corte = max(int(n * 0.8), 2)
    X_train, y_train = X[:corte], y[:corte]
    X_test, y_test = X[corte:], y[corte:]

    pesos, sesgo = _entrenar_regresion_logistica(X_train, y_train)

    # Predicción sobre todos los clientes (inferencia final)
    probs_todos = _predecir_logistica(X, pesos, sesgo)

    # Métrica en prueba (accuracy simple con umbral 0.5)
    metrica = None
    if X_test:
        preds_test = _predecir_logistica(X_test, pesos, sesgo)
        aciertos = sum(
            1 for p, t in zip(preds_test, y_test) if (1 if p >= 0.5 else 0) == t
        )
        metrica = {
            'accuracy': round(aciertos / len(y_test), 4),
            'clientes_entrenados': len(X_train),
            'clientes_prueba': len(y_test),
            'abandono_en_entrenamiento': sum(y_train),
            'metodo': 'regresión logística simple (estándar de Python)',
        }

    # Construir salida ordenada por probabilidad descendente
    resultados = []
    for r, prob in zip(registros, probs_todos):
        resultados.append({
            'cliente_id': r['cliente_id'],
            'cliente_email': r['email'],
            'probabilidad_abandono': round(prob, 4),
            'nivel_riesgo': _nivel_riesgo(prob),
            'recencia_dias': r['recencia'],
            'frecuencia': r['frecuencia'],
            'monetario_total': round(r['monetario'], 2),
            'variables_explicativas': {
                'recencia_dias': r['recencia'],
                'frecuencia_compras': r['frecuencia'],
                'monetario_total': round(r['monetario'], 2),
                'es_abandono_etiquetado': bool(r['abandono']),
            },
        })
    resultados.sort(key=lambda x: -x['probabilidad_abandono'])

    return {
        'tienda_id': tienda.id,
        'tienda_nombre': tienda.nombre,
        'dias_umbral_abandono': dias_umbral_abandono,
        'fecha_referencia': str(fecha_referencia),
        'estado': 'completado',
        'mensaje': 'Riesgo de abandono evaluado con regresión logística simple.',
        'clientes': resultados,
        'metrica': metrica,
    }
