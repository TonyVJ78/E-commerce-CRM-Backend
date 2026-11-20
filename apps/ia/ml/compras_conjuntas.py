"""Productos que se compran juntos: reglas de asociación por pares (soporte, confianza y lift)."""

from collections import Counter
from itertools import combinations

import numpy as np

from .datos import DatosInsuficientes, DatosTienda

TIPO = 'compras_conjuntas'
TITULO = '¿Qué productos se compran juntos?'
ALGORITMO = 'Reglas de asociación por pares (soporte, confianza, lift)'
EXPLICACION = (
    'El modelo revisa los pedidos que llevaron dos o más productos y cuenta qué pares aparecen '
    'juntos más de lo que ocurriría por casualidad. Un lift de 2 significa que, quien compra el '
    'primer producto, compra el segundo el doble de veces que un cliente cualquiera. Sirve para '
    'sugerir productos complementarios y armar combos. Para medirlo, escondió un producto de '
    'pedidos que no usó para aprender y comprobó si lo recomendaba entre sus 5 primeras opciones.'
)

SEMILLA = 42
FRACCION_PRUEBA = 0.25
MINIMO_PEDIDOS_PAR = 3
TOP_PARES = 12
TOP_RECOMENDACIONES = 5
MINIMO_PEDIDOS = 20


class Reglas:
    """Conteos de productos y pares sobre un conjunto de pedidos (canastas)."""

    def __init__(self, canastas: list[frozenset[int]]):
        self.total = len(canastas)
        self.productos = Counter(p for c in canastas for p in c)
        self.pares = Counter(
            par for c in canastas if len(c) > 1 for par in combinations(sorted(c), 2))
        self.vecinos: dict[int, list[tuple[int, int]]] = {}
        for (a, b), n in self.pares.items():
            if n >= MINIMO_PEDIDOS_PAR:
                self.vecinos.setdefault(a, []).append((b, n))
                self.vecinos.setdefault(b, []).append((a, n))

    def recomendar(self, observados: frozenset[int], cantidad: int) -> list[int]:
        """Productos con mayor confianza desde algún producto ya en el pedido; desempata por id."""
        puntajes: dict[int, float] = {}
        for origen in observados:
            for destino, n in self.vecinos.get(origen, ()):
                if destino not in observados:
                    puntajes[destino] = max(puntajes.get(destino, 0.0), n / self.productos[origen])
        ranking = sorted(puntajes, key=lambda p: (-puntajes[p], p))
        return ranking[:cantidad]

    def populares(self, excluidos: frozenset[int], cantidad: int) -> list[int]:
        ranking = sorted((p for p in self.productos if p not in excluidos), key=lambda p: (-self.productos[p], p))
        return ranking[:cantidad]


def evaluar(canastas: list[frozenset[int]]) -> dict:
    """Hit-rate@5: esconde un producto de cada pedido de prueba con 2+ productos y mide si se recomienda."""
    azar = np.random.default_rng(SEMILLA)
    orden = azar.permutation(len(canastas))
    n_prueba = int(round(len(canastas) * FRACCION_PRUEBA))
    prueba = [canastas[i] for i in orden[:n_prueba] if len(canastas[i]) > 1]
    reglas = Reglas([canastas[i] for i in orden[n_prueba:]])

    aciertos_reglas = aciertos_populares = 0
    for canasta in prueba:
        oculto = sorted(canasta)[int(azar.integers(len(canasta)))]
        observados = canasta - {oculto}
        aciertos_reglas += oculto in reglas.recomendar(observados, TOP_RECOMENDACIONES)
        aciertos_populares += oculto in reglas.populares(observados, TOP_RECOMENDACIONES)
    n = len(prueba)
    return {
        'pedidos_prueba': n,
        'hit_rate_5': round(aciertos_reglas / n, 3) if n else 0.0,
        'hit_rate_5_populares': round(aciertos_populares / n, 3) if n else 0.0,
    }


def pares_principales(reglas: Reglas, nombres: dict[int, str]) -> list[dict]:
    filas = []
    for (a, b), n in reglas.pares.items():
        if n < MINIMO_PEDIDOS_PAR:
            continue
        lift = n * reglas.total / (reglas.productos[a] * reglas.productos[b])
        filas.append({
            'producto_a': nombres.get(a, f'Producto {a}'),
            'producto_b': nombres.get(b, f'Producto {b}'),
            'pedidos': n,
            'soporte': round(n / reglas.total, 4),
            'confianza_a_b': round(n / reglas.productos[a], 3),
            'confianza_b_a': round(n / reglas.productos[b], 3),
            'lift': round(lift, 2),
        })
    filas.sort(key=lambda f: (-f['lift'], -f['pedidos'], f['producto_a'], f['producto_b']))
    return filas[:TOP_PARES]


def entrenar(datos: DatosTienda) -> dict:
    canastas = [datos.productos_por_pedido[p] for p in datos.pedido_id.tolist() if p in datos.productos_por_pedido]
    if len(canastas) < MINIMO_PEDIDOS:
        raise DatosInsuficientes(f'Hacen falta al menos {MINIMO_PEDIDOS} pedidos con productos; hay {len(canastas)}.')
    reglas = Reglas(canastas)
    con_varios = sum(1 for c in canastas if len(c) > 1)
    utiles = sum(1 for n in reglas.pares.values() if n >= MINIMO_PEDIDOS_PAR)
    metricas = {
        'pedidos_analizados': len(canastas),
        'pedidos_con_varios': con_varios,
        'pares_distintos': len(reglas.pares),
        'pares_utiles': utiles,
        'minimo_pedidos_par': MINIMO_PEDIDOS_PAR,
        **evaluar(canastas),
    }
    avisos = []
    if utiles == 0:
        avisos.append(
            f'Solo {con_varios} de {len(canastas)} pedidos llevaron 2 o más productos y ningún par '
            f'se repitió {MINIMO_PEDIDOS_PAR} veces: todavía no hay patrones fiables.')
    elif con_varios < 0.2 * len(canastas):
        avisos.append(
            f'Solo {con_varios} de {len(canastas)} pedidos llevaron 2 o más productos; '
            'con tan pocos, las reglas pueden cambiar mucho con nuevas ventas.')
    if utiles and metricas['pedidos_prueba'] and metricas['hit_rate_5'] <= metricas['hit_rate_5_populares']:
        avisos.append(
            'Las reglas no superan a recomendar lo más vendido: en esta tienda los productos '
            'se combinan casi al azar y los pares de abajo son débiles.')
    metricas['avisos'] = avisos
    return {
        'algoritmo': ALGORITMO,
        'parametros': {
            'semilla': SEMILLA,
            'fraccion_prueba': FRACCION_PRUEBA,
            'minimo_pedidos_par': MINIMO_PEDIDOS_PAR,
            'recomendaciones': TOP_RECOMENDACIONES,
        },
        'metricas': metricas,
        'resultados': {'pares': pares_principales(reglas, datos.nombres_producto)},
        'filas_entrenamiento': len(canastas),
    }
