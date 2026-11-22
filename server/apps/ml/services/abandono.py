"""
Servicio de riesgo de abandono de clientes (CU-35, modelo B).

Implementa un clasificador ligero basado en señales RFM (recencia, frecuencia,
valor monetario) sobre pedidos reales de la tienda. Usa solo la biblioteca
estándar de Python.

Definición verificable de abandono (sin fuga temporal):
  Se define una fecha de corte histórica = fecha_referencia -
  `dias_observacion_posterior`. Las variables predictoras (recencia, frecuencia,
  monetario, días como cliente) se calculan EXCLUSIVAMENTE con pedidos
  anteriores o iguales a esa fecha de corte.
  La etiqueta de abandono se mide en el período POSTERIOR al corte:
  abandono=1 si el cliente NO realizó ninguna compra entre el corte y la
  fecha de referencia (última compra registrada en la tienda).

Entrenamiento:
  Regresión logística simple implementada a mano (gradiente descendente) sobre
  features normalizadas. La separación de entrenamiento/prueba es temporal: los
  clientes cuya última compra al corte es más antigua entrenan; los más
  recientes prueban. Nunca se usa información futura para entrenar.

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


def _normalizar(valor, vmin, vmax):
    if vmax == vmin:
        return 0.5
    return (valor - vmin) / (vmax - vmin)


def evaluar_riesgo_abandono(tienda, dias_umbral_abandono=90, dias_observacion_posterior=90):
    """
    Evalúa el riesgo de abandono de los clientes de una tienda.

    Metodología sin fuga temporal:
      - fecha_referencia = última compra registrada en la tienda.
      - fecha_corte = fecha_referencia - dias_observacion_posterior.
      - Features: solo pedidos <= fecha_corte.
      - Etiqueta: abandono=1 si NO hubo compras en (fecha_corte, fecha_referencia].
      - Separación temporal: clientes con última compra al corte más antigua
        entrenan; los más recientes prueban.

    Retorna dict con:
      - tienda_id, tienda_nombre
      - dias_umbral_abandono, dias_observacion_posterior
      - fecha_referencia, fecha_corte
      - estado: 'completado' o 'datos_insuficientes'
      - clientes: lista de {cliente_id, email, probabilidad_abandono,
        nivel_riesgo, recencia_dias, frecuencia, monetario_total,
        variables_explicativas}
      - metrica: {accuracy, precision, recall, f1, matriz_confusion,
        brier_score, clientes_entrenados, clientes_prueba, abandono_en_*,
        baseline_clase_mayoritaria, metodo} o None
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
            'dias_observacion_posterior': dias_observacion_posterior,
            'fecha_referencia': str(hoy),
            'fecha_corte': str(hoy),
            'estado': 'datos_insuficientes',
            'mensaje': 'No hay pedidos válidos en esta tienda.',
            'clientes': [],
            'metrica': None,
        }

    # Fecha de referencia: última compra registrada en la tienda.
    fecha_referencia = max(p.fecha.date() for p in pedidos)
    # Fecha de corte histórica: solo se usará información anterior a este punto.
    fecha_corte = fecha_referencia - timedelta(days=dias_observacion_posterior)

    # Agrupar pedidos por cliente
    por_cliente = defaultdict(list)
    for p in pedidos:
        if p.cliente_id is None:
            continue
        por_cliente[p.cliente_id].append(p)

    # Construir features (antes del corte) y etiqueta (compras después del corte)
    # con reducción adaptiva del período de observación: se busca un corte
    # histórico que deje al menos 5 clientes con historial previo, sin que el
    # corte supere ni iguale la fecha de referencia.
    registros = []
    fecha_corte_usado = fecha_corte
    observacion_usado = dias_observacion_posterior
    for observacion in range(dias_observacion_posterior, 6, -7):
        fecha_corte_candidato = fecha_referencia - timedelta(days=observacion)
        registros_candidato = []
        for cid, ps in por_cliente.items():
            fechas = sorted(p.fecha.date() for p in ps)
            previas = [f for f in fechas if f <= fecha_corte_candidato]
            if len(previas) < 1:
                continue

            ultima_prev = max(previas)
            primera_prev = min(previas)
            recencia = (fecha_corte_candidato - ultima_prev).days
            frecuencia = len(previas)
            monetario = sum(
                float(p.total) for p in ps if p.fecha.date() <= fecha_corte_candidato
            )
            dias_cliente = max((fecha_corte_candidato - primera_prev).days, 1)

            # Etiqueta: ¿compró en el período posterior al corte?
            compro_despues_corte = any(
                fecha_corte_candidato < f <= fecha_referencia for f in fechas
            )
            abandonado = 0 if compro_despues_corte else 1

            registros_candidato.append({
                'cliente_id': cid,
                'email': ps[0].cliente.email if ps[0].cliente else '',
                'ultima_compra_corte': ultima_prev,
                'recencia_corte': recencia,
                'frecuencia_corte': frecuencia,
                'monetario_corte': monetario,
                'dias_cliente_corte': dias_cliente,
                'abandono': abandonado,
            })
        if len(registros_candidato) >= 5:
            registros = registros_candidato
            fecha_corte_usado = fecha_corte_candidato
            observacion_usado = observacion
            break

    if len(registros) < 5:
        return {
            'tienda_id': tienda.id,
            'tienda_nombre': tienda.nombre,
            'dias_umbral_abandono': dias_umbral_abandono,
            'dias_observacion_posterior': observacion_usado,
            'fecha_referencia': str(fecha_referencia),
            'fecha_corte': str(fecha_corte_usado),
            'estado': 'datos_insuficientes',
            'mensaje': (
                f'Solo {len(registros)} cliente(s) con historial previo al corte; '
                f'se requieren al menos 5.'
            ),
            'clientes': [],
            'metrica': None,
        }

    # Separación temporal: ordenar por última compra al corte (más antigua primero)
    registros.sort(key=lambda r: r['ultima_compra_corte'])
    n = len(registros)
    corte_idx = max(int(n * 0.8), 2)
    registros_train = registros[:corte_idx]
    registros_test = registros[corte_idx:]

    # Normalizar features con estadísticos del conjunto de entrenamiento
    recs_train = [r['recencia_corte'] for r in registros_train]
    frecs_train = [r['frecuencia_corte'] for r in registros_train]
    mons_train = [r['monetario_corte'] for r in registros_train]
    dias_train = [r['dias_cliente_corte'] for r in registros_train]

    def construir_X(registros_):
        X = []
        for r in registros_:
            X.append([
                _normalizar(r['recencia_corte'], min(recs_train), max(recs_train)),
                _normalizar(r['frecuencia_corte'], min(frecs_train), max(frecs_train)),
                _normalizar(r['monetario_corte'], min(mons_train), max(mons_train)),
                _normalizar(r['dias_cliente_corte'], 1, max(dias_train)),
            ])
        return X

    X_train = construir_X(registros_train)
    X_test = construir_X(registros_test)
    y_train = [r['abandono'] for r in registros_train]
    y_test = [r['abandono'] for r in registros_test]

    abandonados_train = sum(y_train)
    abandonados_test = sum(y_test)
    if abandonados_train < 1 or (len(y_train) - abandonados_train) < 1:
        return {
            'tienda_id': tienda.id,
            'tienda_nombre': tienda.nombre,
            'dias_umbral_abandono': dias_umbral_abandono,
            'dias_observacion_posterior': dias_observacion_posterior,
            'fecha_referencia': str(fecha_referencia),
            'fecha_corte': str(fecha_corte),
            'estado': 'datos_insuficientes',
            'mensaje': (
                'El conjunto de entrenamiento temporal no contiene ambas clases '
                'de abandono; no se puede aprender sin fuga.'
            ),
            'clientes': [],
            'metrica': None,
        }

    pesos, sesgo = _entrenar_regresion_logistica(X_train, y_train)

    # Métrica en prueba temporal (holdout sin fuga)
    probs_test = _predecir_logistica(X_test, pesos, sesgo)
    y_pred_test = [1 if p >= 0.5 else 0 for p in probs_test]

    metrica = _metricas_clasificacion(y_test, y_pred_test, probs_test)
    metrica['clientes_entrenados'] = len(X_train)
    metrica['clientes_prueba'] = len(X_test)
    metrica['abandono_en_entrenamiento'] = abandonados_train
    metrica['abandono_en_prueba'] = abandonados_test
    metrica['metodo'] = (
        'regresión logística simple (holdout temporal, corte histórico, sin fuga)'
    )

    # Baseline de clase mayoritaria en prueba temporal
    clase_may = 1 if abandonados_train > len(y_train) / 2 else 0
    y_pred_base = [clase_may] * len(y_test)
    metrica['baseline_clase_mayoritaria'] = _metricas_clasificacion(
        y_test, y_pred_base
    )

    # Inferencia final sobre todos los clientes con features hasta fecha_referencia
    # (estado actual), aplicando el modelo entrenado solo con datos previos al corte.
    registros_actual = []
    for cid, ps in por_cliente.items():
        fechas = sorted(p.fecha.date() for p in ps)
        ultima = max(fechas)
        primera = min(fechas)
        recencia = (fecha_referencia - ultima).days
        frecuencia = len(ps)
        monetario = sum(float(p.total) for p in ps)
        dias_cliente = max((fecha_referencia - primera).days, 1)
        registros_actual.append({
            'cliente_id': cid,
            'email': ps[0].cliente.email if ps[0].cliente else '',
            'recencia': recencia,
            'frecuencia': frecuencia,
            'monetario': monetario,
            'dias_cliente': dias_cliente,
        })

    if registros_actual:
        recs_act = [r['recencia'] for r in registros_actual]
        frecs_act = [r['frecuencia'] for r in registros_actual]
        mons_act = [r['monetario'] for r in registros_actual]
        dias_act = [r['dias_cliente'] for r in registros_actual]

        X_actual = []
        for r in registros_actual:
            X_actual.append([
                _normalizar(r['recencia'], min(recs_act), max(recs_act)),
                _normalizar(r['frecuencia'], min(frecs_act), max(frecs_act)),
                _normalizar(r['monetario'], min(mons_act), max(mons_act)),
                _normalizar(r['dias_cliente'], 1, max(dias_act)),
            ])
        probs_actual = _predecir_logistica(X_actual, pesos, sesgo)
    else:
        probs_actual = []

    # Construir salida ordenada por probabilidad descendente
    resultados = []
    for r, prob in zip(registros_actual, probs_actual):
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
                'dias_cliente': r['dias_cliente'],
            },
        })
    resultados.sort(key=lambda x: -x['probabilidad_abandono'])

    return {
        'tienda_id': tienda.id,
        'tienda_nombre': tienda.nombre,
        'dias_umbral_abandono': dias_umbral_abandono,
        'dias_observacion_posterior': observacion_usado,
        'fecha_referencia': str(fecha_referencia),
        'fecha_corte': str(fecha_corte_usado),
        'estado': 'completado',
        'mensaje': (
            'Riesgo de abandono evaluado con regresión logística simple, '
            'features previas al corte y etiqueta en período posterior.'
        ),
        'clientes': resultados,
        'metrica': metrica,
    }
