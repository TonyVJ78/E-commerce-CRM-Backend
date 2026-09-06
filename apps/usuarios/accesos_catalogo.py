"""
Catálogo de la matriz de permisos (CU07 — Accesos Avanzados).

La matriz es **módulo × acción**: cada permiso tiene el código `"<modulo>.<accion>"`
(p. ej. `accesos.editar`, `bitacora.ver`). El frontend arma la grilla partiendo el
código por el punto; el backend exige `PermisoModulo('<modulo>')` en cada vista y
resuelve la acción a partir del método HTTP.

Añadir un módulo nuevo = agregar una fila acá + una migración de datos que siembre
sus 4 permisos y los asigne a los roles que correspondan.
"""

# clave -> etiqueta legible (orden = orden en la grilla)
MODULOS = [
    ('accesos', 'Roles y permisos'),
    ('usuarios', 'Usuarios'),
    ('bitacora', 'Bitácora y auditoría'),
    ('tiendas', 'Tiendas'),
    ('catalogo', 'Catálogo'),
    ('pedidos', 'Pedidos'),
    ('crm', 'CRM'),
    ('marketing', 'Marketing'),
    ('ia', 'IA y recomendaciones'),
]

# clave -> etiqueta; el orden es el de las columnas (CRUD)
ACCIONES = [
    ('ver', 'Ver'),
    ('crear', 'Crear'),
    ('editar', 'Editar'),
    ('eliminar', 'Eliminar'),
]

# Método HTTP -> acción de la matriz
ACCION_POR_METODO = {
    'GET': 'ver',
    'HEAD': 'ver',
    'OPTIONS': 'ver',
    'POST': 'crear',
    'PUT': 'editar',
    'PATCH': 'editar',
    'DELETE': 'eliminar',
}

ETIQUETA_MODULO = dict(MODULOS)
ETIQUETA_ACCION = dict(ACCIONES)


def codigo(modulo, accion):
    return f'{modulo}.{accion}'


def nombre_legible(modulo, accion):
    return f'{ETIQUETA_ACCION[accion]} · {ETIQUETA_MODULO[modulo]}'


def catalogo_completo():
    """[(codigo, nombre), ...] con las 4 acciones de cada módulo."""
    return [
        (codigo(m, a), nombre_legible(m, a))
        for m, _ in MODULOS
        for a, _ in ACCIONES
    ]
