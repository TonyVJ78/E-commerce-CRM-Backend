"""
Ciclo de vida de un pedido (CU-22).

    pendiente ─► procesado ─► enviado ─► entregado
        └───────────┴─► cancelado

`completado` es el estado con el que el checkout creaba los pedidos antes de
CU-22; se trata como `pendiente` para no tener que migrar datos.
"""

PENDIENTE = 'pendiente'
PROCESADO = 'procesado'
ENVIADO = 'enviado'
ENTREGADO = 'entregado'
CANCELADO = 'cancelado'
COMPLETADO_LEGADO = 'completado'

FLUJO = [PENDIENTE, PROCESADO, ENVIADO, ENTREGADO]
ESTADOS = FLUJO + [CANCELADO]

ETIQUETAS = {
    PENDIENTE: 'Pendiente',
    PROCESADO: 'Procesado',
    ENVIADO: 'Enviado',
    ENTREGADO: 'Entregado',
    CANCELADO: 'Cancelado',
}

TRANSICIONES = {
    PENDIENTE: [PROCESADO, CANCELADO],
    PROCESADO: [ENVIADO, CANCELADO],
    ENVIADO: [ENTREGADO],
    ENTREGADO: [],
    CANCELADO: [],
}


def normalizar(estado):
    return PENDIENTE if estado == COMPLETADO_LEGADO else estado


def etiqueta(estado):
    estado = normalizar(estado)
    return ETIQUETAS.get(estado, estado)


def siguientes(estado):
    return list(TRANSICIONES.get(normalizar(estado), []))


def puede_transicionar(actual, nuevo):
    return nuevo in siguientes(actual)
