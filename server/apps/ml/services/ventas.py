"""
Servicio de pronóstico de ventas (CU-35, modelo A).

Implementa una regresión lineal simple (mínimos cuadrados ordinarios) sobre la
serie temporal diaria de ingresos de una tienda. No depende de librerías
externas de ML: solo usa la biblioteca estándar de Python para mantener el
paquete de despliegue ligero y reproducible.

Reglas de negocio:
- Solo se consideran pedidos no cancelados de la tienda indicada.
- Los ingresos se agregan por fecha (día) a partir de ItemPedido.
- Se evita fuga de información: el modelo solo usa fechas <= fecha de corte.
- La validación es temporal (holdout): los primeros datos entrenan, los más
 recientes prueban. Nunca se usa el futuro para predecir el pasado.
"""

from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

from apps.pedidos.models import ItemPedido


def _regresion_lineal_simple(x_vals, y_vals):
    """Ajusta y = a + b*x por mínimos cuadrados. Devuelve (a, b)."""
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
    errores = [abs(t - p) for t, p in zip(y_true, y_pred)]
    mae = sum(errores) / n
    rmse = (sum((t - p) ** 2 for t, p in zip(y_true, y_pred)) / n) ** 0.5
    return round(mae, 4), round(rmse, 4)


def _agrupar_ingresos_por_dia(tienda):
    """Devuelve dict {date: monto_total} de ingresos válidos de la tienda."""
    hoy = timezone.now().date()
    # Ventana razonable: últimos 365 días para no cargar toda la historia.
    fecha_desde = hoy - timedelta(days=365)

    filas = (
        ItemPedido.objects.filter(
            tienda=tienda,
        )
        .exclude(pedido__estado_actual__iexact='cancelado')
        .filter(pedido__fecha__date__gte=fecha_desde)
        .filter(pedido__fecha__date__lte=hoy)
    )

    ingresos = defaultdict(float)
    for item in filas.select_related('pedido'):
        dia = item.pedido.fecha.date()
        ingresos[dia] += float(item.cantidad) * float(item.precio_unitario)
    return dict(ingresos)


def _llenar_serie_diaria(ingresos_por_dia, fecha_desde, fecha_hasta):
    """Rellena días sin ventas con 0 y devuelve lista ordenada de (fecha, monto)."""
    serie = []
    actual = fecha_desde
    while actual <= fecha_hasta:
        serie.append((actual, ingresos_por_dia.get(actual, 0.0)))
        actual += timedelta(days=1)
    return serie


def pronosticar_ventas(tienda, horizonte_dias=7):
    """
    Ejecuta el pronóstico de ventas de una tienda.

    Retorna un dict con:
      - tienda_id, tienda_nombre
      - periodo_inicio, periodo_fin (rango histórico usado)
      - horizonte_dias
      - fechas_previstas: lista de {fecha, valor_previsto}
      - metrica: {mae, rmse, datos_entrenamiento, datos_prueba} o None si insuficiente
      - estado: 'completado' o 'datos_insuficientes'
    """
    hoy = timezone.now().date()
    fecha_desde = hoy - timedelta(days=365)
    fecha_hasta = hoy

    ingresos = _agrupar_ingresos_por_dia(tienda)
    if not ingresos:
        return {
            'tienda_id': tienda.id,
            'tienda_nombre': tienda.nombre,
            'periodo_inicio': str(fecha_desde),
            'periodo_fin': str(fecha_hasta),
            'horizonte_dias': horizonte_dias,
            'estado': 'datos_insuficientes',
            'mensaje': 'No hay ventas válidas en el último año para esta tienda.',
            'fechas_previstas': [],
            'metrica': None,
        }

    # Serie diaria completa
    serie_completa = _llenar_serie_diaria(ingresos, fecha_desde, fecha_hasta)
    fechas = [s[0] for s in serie_completa]
    valores = [s[1] for s in serie_completa]

    # Determinar fecha de corte (último día con dato real)
    fecha_corte = max(ingresos.keys())

    # --- Entrenamiento: usar datos hasta fecha_corte ---
    datos_train = [
        (i, v) for i, (f, v) in enumerate(serie_completa) if f <= fecha_corte
    ]
    if len(datos_train) < 7:
        return {
            'tienda_id': tienda.id,
            'tienda_nombre': tienda.nombre,
            'periodo_inicio': str(fecha_desde),
            'periodo_fin': str(fecha_hasta),
            'horizonte_dias': horizonte_dias,
            'estado': 'datos_insuficientes',
            'mensaje': 'Muy pocos días con ventas para entrenar el modelo.',
            'fechas_previstas': [],
            'metrica': None,
        }

    x_train = [d for d, _ in datos_train]
    y_train = [v for _, v in datos_train]

    # --- Validación temporal holdout (solo si hay suficientes datos) ---
    metrica = None
    n_total = len(datos_train)
    if n_total >= 14:
        corte_holdout = int(n_total * 0.8)
        # Ajustar únicamente con el pasado para evaluar el tramo más reciente.
        # El ajuste final para pronosticar se realiza después, usando toda la
        # historia disponible; así el holdout no filtra información futura.
        a_eval, b_eval = _regresion_lineal_simple(
            x_train[:corte_holdout], y_train[:corte_holdout]
        )
        x_test = x_train[corte_holdout:]
        y_test = y_train[corte_holdout:]
        y_pred = [a_eval + b_eval * x for x in x_test]
        mae, rmse = _mae_rmse(y_test, y_pred)
        # Baseline ingenuo: valor medio del entrenamiento predecido constantemente.
        valor_medio = sum(y_train[:corte_holdout]) / corte_holdout
        mae_base, rmse_base = _mae_rmse(y_test, [valor_medio] * len(y_test))
        metrica = {
            'mae': mae,
            'rmse': rmse,
            'datos_entrenamiento': corte_holdout,
            'datos_prueba': len(x_test),
            'baseline_mae': round(mae_base, 4),
            'baseline_rmse': round(rmse_base, 4),
            'metodo': 'holdout temporal',
        }

    # Modelo final: toda la historia hasta la fecha de corte, solo para la
    # inferencia futura (nunca para calcular la métrica anterior).
    a, b = _regresion_lineal_simple(x_train, y_train)

    # --- Predicción futura (días después de fecha_corte) ---
    indice_ultimo = x_train[-1]
    fechas_previstas = []
    for paso in range(1, horizonte_dias + 1):
        fecha_pred = fecha_corte + timedelta(days=paso)
        x_pred = indice_ultimo + paso
        valor = max(0.0, a + b * x_pred)
        fechas_previstas.append({
            'fecha': str(fecha_pred),
            'valor_previsto': round(valor, 2),
        })

    return {
        'tienda_id': tienda.id,
        'tienda_nombre': tienda.nombre,
        'periodo_inicio': str(fecha_desde),
        'periodo_fin': str(fecha_hasta),
        'fecha_corte': str(fecha_corte),
        'horizonte_dias': horizonte_dias,
        'estado': 'completado',
        'mensaje': 'Pronóstico generado con regresión lineal simple.',
        'fechas_previstas': fechas_previstas,
        'metrica': metrica,
        'coeficientes': {'intercepto': round(a, 4), 'pendiente': round(b, 6)},
    }
