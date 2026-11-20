"""Riesgo de abandono de clientes: regresión logística entrenada con descenso de gradiente."""

from datetime import date, timedelta

import numpy as np

from .datos import DatosInsuficientes, DatosTienda, eventos_por_cliente, nombres_clientes

TIPO = 'riesgo_abandono'
TITULO = '¿Qué clientes podrían dejar de comprar?'
ALGORITMO = 'Regresión logística con regularización L2'
EXPLICACION = (
    'Para cada cliente el modelo estima la probabilidad de que no vuelva a comprar en los próximos '
    '60 días, a partir de cuánto y con qué frecuencia compró, cuándo fue su última compra, qué '
    'calificaciones dejó y cuánto navegó en la tienda. Aprendió mirando el pasado: tomó una fecha '
    'de hace 60 días, calculó esos datos solo hasta ahí y comprobó quién volvió a comprar después. '
    'Se validó con clientes que no usó para aprender.'
)

DIAS_VENTANA = 60
DIAS_EVENTOS = 30
DIAS_CLIENTE_ACTIVO = 180
FRACCION_PRUEBA = 0.25
SEMILLA = 42
L2 = 0.01
TASA_APRENDIZAJE = 0.5
ITERACIONES = 1500
MINIMO_CLIENTES = 60
MINIMO_POR_CLASE = 8
UMBRAL = 0.5
TOP_RIESGO = 20

VARIABLES = [
    ('recencia_dias', 'Días desde la última compra'),
    ('frecuencia', 'Cantidad de pedidos'),
    ('monto_total', 'Monto total comprado'),
    ('ticket_promedio', 'Ticket promedio'),
    ('dias_entre_compras', 'Días promedio entre compras'),
    ('calificacion_promedio', 'Calificación promedio'),
    ('eventos_30d', 'Actividad en la tienda (30 días previos)'),
    ('uso_cupon', 'Usó un cupón'),
]


def variables_clientes(datos: DatosTienda, corte: date) -> tuple[np.ndarray, np.ndarray]:
    """Variables de cada cliente con compras antes de `corte`, usando solo datos previos a esa fecha."""
    corte_dia = corte.toordinal()
    previos = datos.pedido_dia < corte_dia
    clientes, inverso = np.unique(datos.pedido_cliente[previos], return_inverse=True)
    dias = datos.pedido_dia[previos]
    n = np.bincount(inverso)
    monto = np.bincount(inverso, weights=datos.pedido_total[previos])
    ultima = np.zeros(len(clientes))
    np.maximum.at(ultima, inverso, dias)
    primera = np.full(len(clientes), np.inf)
    np.minimum.at(primera, inverso, dias)
    recencia = corte_dia - ultima
    # Con una sola compra no hay cadencia: se toma el tiempo transcurrido como única espera.
    entre_compras = np.where(n > 1, (ultima - primera) / np.maximum(n - 1, 1), recencia)
    cupon = np.bincount(inverso, weights=datos.pedido_con_cupon[previos].astype(float)) > 0

    resenas_previas = datos.resena_dia < corte_dia
    calificacion = np.zeros(len(clientes))
    if resenas_previas.any():
        posicion = np.minimum(
            np.searchsorted(clientes, datos.resena_cliente[resenas_previas]), len(clientes) - 1)
        es_cliente = clientes[posicion] == datos.resena_cliente[resenas_previas]
        notas = datos.resena_calificacion[resenas_previas][es_cliente]
        suma = np.bincount(posicion[es_cliente], weights=notas, minlength=len(clientes))
        cuenta = np.bincount(posicion[es_cliente], minlength=len(clientes))
        promedio_global = datos.resena_calificacion[resenas_previas].mean()
        calificacion = np.where(cuenta > 0, suma / np.maximum(cuenta, 1), promedio_global)

    eventos = eventos_por_cliente(datos.tienda_id, corte - timedelta(days=DIAS_EVENTOS), corte)
    actividad = np.array([eventos.get(int(c), 0) for c in clientes], dtype=float)

    X = np.column_stack([
        recencia,
        np.log1p(n),
        np.log1p(monto),
        np.log1p(monto / n),
        entre_compras,
        calificacion,
        np.log1p(actividad),
        cupon.astype(float),
    ])
    return clientes, X


def etiquetas_abandono(datos: DatosTienda, clientes: np.ndarray, corte: date, hasta: date) -> np.ndarray:
    """1 si el cliente no compró entre `corte` y `hasta` (ambos inclusive)."""
    en_ventana = (datos.pedido_dia >= corte.toordinal()) & (datos.pedido_dia <= hasta.toordinal())
    volvieron = np.unique(datos.pedido_cliente[en_ventana])
    return (~np.isin(clientes, volvieron)).astype(float)


def _sigmoide(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def ajustar_logistica(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    """Descenso de gradiente por lotes sobre la pérdida logarítmica más penalización L2."""
    pesos = np.zeros(X.shape[1])
    sesgo = 0.0
    n = len(y)
    for _ in range(ITERACIONES):
        error = _sigmoide(X @ pesos + sesgo) - y
        pesos -= TASA_APRENDIZAJE * (X.T @ error / n + L2 * pesos)
        sesgo -= TASA_APRENDIZAJE * error.mean()
    return pesos, sesgo


def auc(y: np.ndarray, puntaje: np.ndarray) -> float:
    """Área bajo la curva ROC por rangos (Mann-Whitney), con rango medio en empates."""
    orden = np.argsort(puntaje, kind='mergesort')
    ordenado = puntaje[orden]
    rangos = np.empty(len(puntaje))
    inicio = 0
    while inicio < len(ordenado):
        fin = inicio
        while fin + 1 < len(ordenado) and ordenado[fin + 1] == ordenado[inicio]:
            fin += 1
        rangos[orden[inicio:fin + 1]] = (inicio + fin) / 2 + 1
        inicio = fin + 1
    positivos = y == 1
    n_pos = positivos.sum()
    n_neg = len(y) - n_pos
    return float((rangos[positivos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def particion_estratificada(y: np.ndarray, fraccion_prueba: float, semilla: int) -> tuple[np.ndarray, np.ndarray]:
    azar = np.random.default_rng(semilla)
    entrenamiento, prueba = [], []
    for clase in (0.0, 1.0):
        indices = azar.permutation(np.flatnonzero(y == clase))
        n_prueba = max(1, int(round(len(indices) * fraccion_prueba)))
        prueba.append(indices[:n_prueba])
        entrenamiento.append(indices[n_prueba:])
    return np.sort(np.concatenate(entrenamiento)), np.sort(np.concatenate(prueba))


def _metricas_clasificacion(y: np.ndarray, probabilidad: np.ndarray) -> dict:
    prediccion = probabilidad >= UMBRAL
    verdaderos = float(np.sum(prediccion & (y == 1)))
    predichos = float(prediccion.sum())
    reales = float((y == 1).sum())
    return {
        'auc': round(auc(y, probabilidad), 3),
        'exactitud': round(float((prediccion == (y == 1)).mean()), 3),
        'precision': round(verdaderos / predichos, 3) if predichos else 0.0,
        'exhaustividad': round(verdaderos / reales, 3) if reales else 0.0,
    }


def _estandarizar(X: np.ndarray, media: np.ndarray, desviacion: np.ndarray) -> np.ndarray:
    return (X - media) / desviacion


def entrenar(datos: DatosTienda) -> dict:
    hasta = datos.hasta
    corte = hasta - timedelta(days=DIAS_VENTANA - 1)
    clientes, X = variables_clientes(datos, corte)
    if len(clientes) < MINIMO_CLIENTES:
        raise DatosInsuficientes(
            f'Hacen falta al menos {MINIMO_CLIENTES} clientes con compras de hace más de '
            f'{DIAS_VENTANA} días; hay {len(clientes)}.')
    y = etiquetas_abandono(datos, clientes, corte, hasta)
    if min(y.sum(), len(y) - y.sum()) < MINIMO_POR_CLASE:
        raise DatosInsuficientes(
            f'Hacen falta al menos {MINIMO_POR_CLASE} clientes que abandonaron y {MINIMO_POR_CLASE} que '
            f'siguieron comprando para aprender la diferencia; hay {int(y.sum())} y {int(len(y) - y.sum())}.')

    entrenamiento, prueba = particion_estratificada(y, FRACCION_PRUEBA, SEMILLA)
    media = X[entrenamiento].mean(axis=0)
    desviacion = X[entrenamiento].std(axis=0)
    desviacion[desviacion == 0] = 1.0
    pesos, sesgo = ajustar_logistica(_estandarizar(X[entrenamiento], media, desviacion), y[entrenamiento])
    probabilidad_prueba = _sigmoide(_estandarizar(X[prueba], media, desviacion) @ pesos + sesgo)

    metricas = _metricas_clasificacion(y[prueba], probabilidad_prueba)
    metricas.update({
        'tasa_base': round(float(y.mean()), 3),
        'clientes_entrenamiento': int(len(entrenamiento)),
        'clientes_prueba': int(len(prueba)),
        'dias_ventana': DIAS_VENTANA,
        'fecha_corte': corte.isoformat(),
    })
    importancia = sorted(
        ({'variable': clave, 'etiqueta': etiqueta, 'coeficiente': round(float(p), 3)}
         for (clave, etiqueta), p in zip(VARIABLES, pesos)),
        key=lambda f: -abs(f['coeficiente']),
    )

    # Los clientes que llevan más de DIAS_CLIENTE_ACTIVO días sin comprar ya se dan por perdidos.
    clientes_hoy, X_hoy = variables_clientes(datos, hasta + timedelta(days=1))
    activos = X_hoy[:, 0] <= DIAS_CLIENTE_ACTIVO
    probabilidad_hoy = _sigmoide(_estandarizar(X_hoy[activos], media, desviacion) @ pesos + sesgo)
    ids_activos = clientes_hoy[activos]
    peores = np.argsort(-probabilidad_hoy, kind='mergesort')[:TOP_RIESGO]
    identidad = nombres_clientes([int(ids_activos[i]) for i in peores])
    en_riesgo = []
    for i in peores:
        cliente_id = int(ids_activos[i])
        pedidos_cliente = datos.pedido_cliente == cliente_id
        nombre, correo = identidad[cliente_id]
        en_riesgo.append({
            'cliente_id': cliente_id,
            'nombre': nombre,
            'correo': correo,
            'probabilidad': round(float(probabilidad_hoy[i]), 3),
            'ultima_compra': date.fromordinal(int(datos.pedido_dia[pedidos_cliente].max())).isoformat(),
            'pedidos': int(pedidos_cliente.sum()),
        })

    return {
        'algoritmo': ALGORITMO,
        'parametros': {
            'semilla': SEMILLA,
            'l2': L2,
            'tasa_aprendizaje': TASA_APRENDIZAJE,
            'iteraciones': ITERACIONES,
            'umbral': UMBRAL,
            'variables': [clave for clave, _ in VARIABLES],
            'pesos': [float(p) for p in pesos],
            'sesgo': float(sesgo),
            'media': [float(m) for m in media],
            'desviacion': [float(d) for d in desviacion],
        },
        'metricas': metricas,
        'resultados': {
            'importancia': importancia,
            'clientes_puntuados': int(activos.sum()),
            'dias_cliente_activo': DIAS_CLIENTE_ACTIVO,
            'distribucion': {
                'bajo': int(np.sum(probabilidad_hoy < 0.33)),
                'medio': int(np.sum((probabilidad_hoy >= 0.33) & (probabilidad_hoy < 0.66))),
                'alto': int(np.sum(probabilidad_hoy >= 0.66)),
            },
            'en_riesgo': en_riesgo,
        },
        'filas_entrenamiento': int(len(entrenamiento)),
    }
