"""Pronóstico de ventas diarias: regresión ridge con tendencia, día de la semana y estacionalidad anual."""

from datetime import date

import numpy as np

from .datos import DatosInsuficientes, DatosTienda, serie_diaria

TIPO = 'pronostico_ventas'
TITULO = '¿Cuánto venderé los próximos 30 días?'
ALGORITMO = 'Regresión lineal ridge (forma cerrada)'
EXPLICACION = (
    'El modelo aprende de tus ventas diarias tres cosas: si venden más o menos con el tiempo, '
    'qué días de la semana se vende más y si hay temporadas altas en el año. Con eso proyecta '
    'los próximos 30 días y dibuja una banda donde caerían las ventas el 80 % de las veces. '
    'Para saber si sirve, lo probó contra los últimos 28 días reales, que no vio al aprender, '
    'y lo comparó con repetir la última semana conocida.'
)

DIAS_VALIDACION = 28
DIAS_PRONOSTICO = 30
DIAS_HISTORICO = 90
MINIMO_DIAS = 120
ARMONICOS_ANUALES = 2
# Con menos de ~10 meses de historia el ciclo anual no se distingue de la tendencia y distorsiona el pronóstico.
MINIMO_DIAS_ESTACIONALIDAD = 300
COLUMNAS_SIN_ESTACIONALIDAD = 8
LAMBDA_RIDGE = 1.0
Z_80 = 1.2816
PERIODO_ANUAL = 365.2425


def matriz_diseno(dias: np.ndarray, dia_inicial: int, armonicos: int) -> np.ndarray:
    """Columnas: constante, tendencia (años), día de la semana (lunes de referencia) y Fourier anual."""
    tendencia = (dias - dia_inicial) / 365.0
    dia_semana = (dias - 1) % 7
    semana = np.stack([(dia_semana == d).astype(float) for d in range(1, 7)], axis=1)
    fase = 2 * np.pi * dias / PERIODO_ANUAL
    fourier = np.concatenate(
        [np.stack([np.sin(k * fase), np.cos(k * fase)], axis=1) for k in range(1, armonicos + 1)],
        axis=1,
    ) if armonicos else np.empty((len(dias), 0))
    return np.column_stack([np.ones(len(dias)), tendencia, semana, fourier])


def ajustar_ridge(X: np.ndarray, y: np.ndarray, lam: float) -> np.ndarray:
    """Mínimos cuadrados con penalización L2 en todos los coeficientes salvo la constante."""
    penalizacion = lam * np.eye(X.shape[1])
    penalizacion[0, 0] = 0.0
    return np.linalg.solve(X.T @ X + penalizacion, X.T @ y)


def _ajustar_serie(dias: np.ndarray, ingresos: np.ndarray) -> tuple[np.ndarray, float, float]:
    escala = float(ingresos.mean()) or 1.0
    armonicos = ARMONICOS_ANUALES if len(dias) >= MINIMO_DIAS_ESTACIONALIDAD else 0
    X = matriz_diseno(dias, int(dias[0]), armonicos)
    # Se estandarizan las columnas para que la penalización afecte igual a la tendencia que a los dummies.
    media = X[:, 1:].mean(axis=0)
    desviacion = X[:, 1:].std(axis=0)
    desviacion[desviacion == 0] = 1.0
    X_estandar = np.column_stack([X[:, 0], (X[:, 1:] - media) / desviacion])
    pesos_estandar = ajustar_ridge(X_estandar, ingresos / escala, LAMBDA_RIDGE)
    pesos = np.concatenate([[0.0], pesos_estandar[1:] / desviacion])
    pesos[0] = pesos_estandar[0] - float(media @ pesos[1:])
    residuos = ingresos - (X @ pesos) * escala
    sigma = float(np.sqrt(np.sum(residuos ** 2) / max(len(dias) - X.shape[1], 1)))
    return pesos, escala, sigma


def _predecir(pesos: np.ndarray, escala: float, dias: np.ndarray, dia_inicial: int) -> np.ndarray:
    armonicos = (len(pesos) - COLUMNAS_SIN_ESTACIONALIDAD) // 2
    return np.maximum(matriz_diseno(dias, dia_inicial, armonicos) @ pesos * escala, 0.0)


def _error_porcentual(real: np.ndarray, estimado: np.ndarray) -> float:
    con_ventas = real > 0
    if not con_ventas.any():
        return 0.0
    return float(np.mean(np.abs(real - estimado)[con_ventas] / real[con_ventas]) * 100)


def _fechas(dias: np.ndarray) -> list[str]:
    return [date.fromordinal(int(d)).isoformat() for d in dias]


def _redondear(valores: np.ndarray) -> list[float]:
    return [round(float(v), 2) for v in valores]


def evaluar(dias: np.ndarray, ingresos: np.ndarray) -> dict:
    """Entrena sin los últimos `DIAS_VALIDACION` días y mide el error sobre ellos."""
    corte = len(dias) - DIAS_VALIDACION
    pesos, escala, sigma = _ajustar_serie(dias[:corte], ingresos[:corte])
    real = ingresos[corte:]
    modelo = _predecir(pesos, escala, dias[corte:], int(dias[0]))
    # Con horizonte de 28 días no se conoce la semana inmediata anterior: se repite la última semana vista.
    base = np.array([ingresos[corte - 7 + (i % 7)] for i in range(DIAS_VALIDACION)])
    mae = float(np.mean(np.abs(real - modelo)))
    mae_base = float(np.mean(np.abs(real - base)))
    dentro = (real >= np.maximum(modelo - Z_80 * sigma, 0)) & (real <= modelo + Z_80 * sigma)
    return {
        'metricas': {
            'dias_validacion': DIAS_VALIDACION,
            'mae': round(mae, 2),
            'mape': round(_error_porcentual(real, modelo), 1),
            'mae_base': round(mae_base, 2),
            'mape_base': round(_error_porcentual(real, base), 1),
            'mejora_mae_pct': round((1 - mae / mae_base) * 100, 1) if mae_base else 0.0,
            'error_total_pct': round(abs(modelo.sum() - real.sum()) / real.sum() * 100, 1) if real.sum() else 0.0,
            'error_total_base_pct': round(abs(base.sum() - real.sum()) / real.sum() * 100, 1) if real.sum() else 0.0,
            'cobertura_intervalo_pct': round(float(dentro.mean()) * 100, 1),
        },
        'validacion': {
            'fechas': _fechas(dias[corte:]),
            'real': _redondear(real),
            'modelo': _redondear(modelo),
            'base': _redondear(base),
        },
    }


def pronosticar(dias: np.ndarray, ingresos: np.ndarray) -> dict:
    """Reentrena con toda la serie y proyecta los próximos `DIAS_PRONOSTICO` días con banda del 80 %."""
    pesos, escala, sigma = _ajustar_serie(dias, ingresos)
    futuros = np.arange(dias[-1] + 1, dias[-1] + 1 + DIAS_PRONOSTICO)
    central = _predecir(pesos, escala, futuros, int(dias[0]))
    ultimos = ingresos[-DIAS_PRONOSTICO:].sum()
    return {
        'parametros': {
            'lambda_ridge': LAMBDA_RIDGE,
            'armonicos_anuales': (len(pesos) - COLUMNAS_SIN_ESTACIONALIDAD) // 2,
            'coeficientes': [float(p) for p in pesos],
            'escala': escala,
            'sigma_residuos': sigma,
        },
        'resultados': {
            'historico': {
                'fechas': _fechas(dias[-DIAS_HISTORICO:]),
                'valores': _redondear(ingresos[-DIAS_HISTORICO:]),
            },
            'pronostico': {
                'fechas': _fechas(futuros),
                'valores': _redondear(central),
                'inferior': _redondear(np.maximum(central - Z_80 * sigma, 0.0)),
                'superior': _redondear(central + Z_80 * sigma),
            },
            'total_pronosticado': round(float(central.sum()), 2),
            'total_ultimos_dias': round(float(ultimos), 2),
            'variacion_pct': round(float((central.sum() / ultimos - 1) * 100), 1) if ultimos else None,
            'dias_pronostico': DIAS_PRONOSTICO,
        },
    }


def entrenar(datos: DatosTienda) -> dict:
    if len(datos.pedido_id) == 0:
        raise DatosInsuficientes('La tienda aún no tiene pedidos.')
    dias, ingresos = serie_diaria(datos)
    if len(dias) < MINIMO_DIAS:
        raise DatosInsuficientes(
            f'Hacen falta al menos {MINIMO_DIAS} días de historia de ventas; hay {len(dias)}.')
    evaluacion = evaluar(dias, ingresos)
    proyeccion = pronosticar(dias, ingresos)
    proyeccion['resultados']['validacion'] = evaluacion['validacion']
    return {
        'algoritmo': ALGORITMO,
        'parametros': proyeccion['parametros'],
        'metricas': evaluacion['metricas'],
        'resultados': proyeccion['resultados'],
        'filas_entrenamiento': len(dias),
    }
