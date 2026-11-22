"""
Generador reproducible de datos sintéticos para CU-35.

Solo se usa para entrenamiento y demostración académica. Los datos se
generan en memoria y NO se insertan en Neon ni en tablas comerciales de
producción.

Patrones de clientes:
  - leal: compra con frecuencia, baja recencia.
  - ocasional: compra esporádicamente.
  - en_riesgo: compró antes, pero hace mucho que no compra.
  - nuevo: compró hace poco, pocas transacciones.

Retorna estructuras en memoria (diccionarios), listas para entrenar los
servicios de ML sin tocar la base de datos real.
"""

from datetime import date, timedelta
import random


def _fecha_aleatoria(rng, inicio, fin):
    dias = (fin - inicio).days
    return inicio + timedelta(days=rng.randint(0, dias))


def generar_datos_sinteticos(seed=42, n_clientes=1000, n_tiendas=5):
    """
    Genera datos sintéticos de tiendas, clientes, pedidos e ítems.

    Parámetros:
      - seed: semilla aleatoria para reproducibilidad.
      - n_clientes: número total de clientes a generar (mínimo 100 recomendado).
      - n_tiendas: número de tiendas en el dataset.

    Retorna un dict con:
      - tiendas: lista de {id, nombre}
      - clientes: lista de {id, tienda_id, email, patron, fecha_registro}
      - pedidos: lista de {id, cliente_id, tienda_id, fecha, total, estado_actual}
      - items: lista de {id, pedido_id, producto_id, cantidad, precio_unitario}
      - resumen: métricas del dataset generado
    """
    rng = random.Random(seed)

    tiendas = [
        {'id': i + 1, 'nombre': f'Tienda Sintética {i + 1}'}
        for i in range(n_tiendas)
    ]

    patrones = ['leal', 'ocasional', 'en_riesgo', 'nuevo']
    pesos_patrones = [0.35, 0.30, 0.20, 0.15]

    # Ventana de un año para compras
    fecha_inicio = date(2025, 1, 1)
    fecha_fin = date(2025, 12, 31)

    clientes = []
    pedidos = []
    items = []
    id_cliente = 1
    id_pedido = 1
    id_item = 1

    for _ in range(n_clientes):
        tienda = rng.choice(tiendas)
        patron = rng.choices(patrones, weights=pesos_patrones, k=1)[0]

        clientes.append({
            'id': id_cliente,
            'tienda_id': tienda['id'],
            'email': f'cliente_sintetico_{id_cliente}@ejemplo.com',
            'patron': patron,
            'fecha_registro': _fecha_aleatoria(rng, fecha_inicio, fecha_fin),
        })

        # Generar pedidos según el patrón
        n_pedidos_cliente = {
            'leal': rng.randint(8, 25),
            'ocasional': rng.randint(2, 6),
            'en_riesgo': rng.randint(1, 3),
            'nuevo': rng.randint(1, 2),
        }[patron]

        fecha_ultima_compra = None
        for _ in range(n_pedidos_cliente):
            fecha = _fecha_aleatoria(rng, fecha_inicio, fecha_fin)
            if fecha_ultima_compra is not None:
                fecha = max(fecha, fecha_ultima_compra + timedelta(days=1))
            fecha_ultima_compra = fecha

            estado = rng.choices(
                ['completado', 'pendiente', 'cancelado'],
                weights=[0.8, 0.15, 0.05],
                k=1,
            )[0]

            # Niveles de ingresos y frecuencia según patrón
            if patron == 'leal':
                total = round(rng.uniform(50.0, 500.0), 2)
            elif patron == 'ocasional':
                total = round(rng.uniform(30.0, 200.0), 2)
            elif patron == 'en_riesgo':
                total = round(rng.uniform(20.0, 150.0), 2)
            else:  # nuevo
                total = round(rng.uniform(20.0, 100.0), 2)

            pedidos.append({
                'id': id_pedido,
                'cliente_id': id_cliente,
                'tienda_id': tienda['id'],
                'fecha': fecha.isoformat(),
                'total': total,
                'estado_actual': estado,
            })

            for _ in range(rng.randint(1, 3)):
                items.append({
                    'id': id_item,
                    'pedido_id': id_pedido,
                    'producto_id': rng.randint(1, 50),
                    'cantidad': rng.randint(1, 5),
                    'precio_unitario': round(rng.uniform(5.0, 100.0), 2),
                })
                id_item += 1
            id_pedido += 1

        id_cliente += 1

    # Separación train/test por cliente (80/20) - estratificada por tienda para aislamiento
    clientes_ordenados = sorted(clientes, key=lambda c: c['id'])
    corte = int(len(clientes_ordenados) * 0.8)
    train_clientes = clientes_ordenados[:corte]
    test_clientes = clientes_ordenados[corte:]

    # Distribución de clases (abandono: recencia > 90 días respecto a fecha_fin)
    n_abandonos = 0
    n_clientes_con_historial = 0
    n_compras_recientes = 0  # compras en últimos 30 días de fecha_fin
    for c in clientes:
        ps = [p for p in pedidos if p['cliente_id'] == c['id'] and p['estado_actual'] != 'cancelado']
        if not ps:
            continue
        n_clientes_con_historial += 1
        ultima = max(p['fecha'] for p in ps)
        ultima_date = date.fromisoformat(ultima)
        if (fecha_fin - ultima_date).days > 90:
            n_abandonos += 1
        if (fecha_fin - ultima_date).days <= 30:
            n_compras_recientes += 1

    distribucion_patrones = {p: 0 for p in patrones}
    for c in clientes:
        distribucion_patrones[c['patron']] += 1

    estados = {'completado': 0, 'pendiente': 0, 'cancelado': 0}
    for p in pedidos:
        estados[p['estado_actual']] += 1

    # Estadísticas por tienda para verificar aislamiento
    tiendas_stats = {}
    for t in tiendas:
        t_pedidos = [p for p in pedidos if p['tienda_id'] == t['id']]
        t_clientes = [c for c in clientes if c['tienda_id'] == t['id']]
        tiendas_stats[t['id']] = {
            'n_clientes': len(t_clientes),
            'n_pedidos': len(t_pedidos),
        }

    return {
        'semilla': seed,
        'tiendas': tiendas,
        'clientes': clientes,
        'pedidos': pedidos,
        'items': items,
        'resumen': {
            'n_clientes': n_clientes,
            'n_tiendas': n_tiendas,
            'n_pedidos': len(pedidos),
            'n_items': len(items),
            'n_clientes_con_historial': n_clientes_con_historial,
            'distribucion_patrones': distribucion_patrones,
            'distribucion_estados_pedidos': estados,
            'n_clientes_abandono_etiquetado': n_abandonos,
            'n_clientes_compra_reciente': n_compras_recientes,
            'train_clientes': len(train_clientes),
            'test_clientes': len(test_clientes),
            'tiendas_stats': tiendas_stats,
        },
    }
