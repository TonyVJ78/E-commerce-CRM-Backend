"""
Data migration (CU07 — Accesos Avanzados):
Reemplaza el catálogo plano de 0005 por una matriz módulo × acción.

- Códigos nuevos: "<modulo>.<accion>" con accion ∈ {ver, crear, editar, eliminar}.
- Se borran los códigos sueltos de 0005 (ver_bitacora, gestionar_accesos, …).
- Mapeo a roles semilla equivalente al de 0005 (administrador = todo, empresa =
  tiendas/catálogo/pedidos, cliente = nada).

Sin cambios de esquema: solo filas en `permiso` y `rol_permiso`.
"""

from django.db import migrations

# (clave, etiqueta) — el orden define la grilla del frontend
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
ACCIONES = [('ver', 'Ver'), ('crear', 'Crear'), ('editar', 'Editar'), ('eliminar', 'Eliminar')]

ETIQUETA_MODULO = dict(MODULOS)
ETIQUETA_ACCION = dict(ACCIONES)

# rol -> módulos con los 4 permisos
ROL_MODULOS = {
    'administrador': [m for m, _ in MODULOS],
    'empresa': ['tiendas', 'catalogo', 'pedidos'],
    'cliente': [],
}

# Códigos planos sembrados por 0005, ahora obsoletos
CODIGOS_0005 = [
    'ver_bitacora', 'gestionar_accesos', 'ver_dashboard_admin',
    'crear_tienda', 'gestionar_catalogo', 'gestionar_pedidos', 'ver_panel_vendedor',
]

# Estado de 0005 para la marcha atrás
PERMISOS_0005 = [
    ('ver_bitacora', 'Ver bitácora de accesos y auditoría'),
    ('gestionar_accesos', 'Gestionar roles, permisos y usuarios'),
    ('ver_dashboard_admin', 'Ver panel de administración'),
    ('crear_tienda', 'Crear y administrar tiendas'),
    ('gestionar_catalogo', 'Gestionar catálogo de productos'),
    ('gestionar_pedidos', 'Gestionar pedidos y envíos'),
    ('ver_panel_vendedor', 'Ver panel del vendedor'),
]
ROL_PERMISOS_0005 = {
    'administrador': ['ver_bitacora', 'gestionar_accesos', 'ver_dashboard_admin'],
    'empresa': ['crear_tienda', 'gestionar_catalogo', 'gestionar_pedidos', 'ver_panel_vendedor'],
    'cliente': [],
}


def _sembrar(apps, mapa_permisos, rol_a_codigos):
    Rol = apps.get_model('usuarios', 'Rol')
    Permiso = apps.get_model('usuarios', 'Permiso')
    RolPermiso = apps.get_model('usuarios', 'RolPermiso')

    por_codigo = {}
    for cod, nombre in mapa_permisos:
        p, _ = Permiso.objects.get_or_create(codigo=cod, defaults={'nombre': nombre})
        por_codigo[cod] = p

    for nombre_rol, codigos in rol_a_codigos.items():
        try:
            rol = Rol.objects.get(nombre=nombre_rol)
        except Rol.DoesNotExist:
            continue
        for cod in codigos:
            RolPermiso.objects.get_or_create(rol=rol, permiso=por_codigo[cod])


def _borrar(apps, codigos):
    Permiso = apps.get_model('usuarios', 'Permiso')
    RolPermiso = apps.get_model('usuarios', 'RolPermiso')
    RolPermiso.objects.filter(permiso__codigo__in=codigos).delete()
    Permiso.objects.filter(codigo__in=codigos).delete()


def aplicar(apps, schema_editor):
    matriz = [
        (f'{m}.{a}', f'{ETIQUETA_ACCION[a]} · {ETIQUETA_MODULO[m]}')
        for m, _ in MODULOS
        for a, _ in ACCIONES
    ]
    rol_a_codigos = {
        rol: [f'{m}.{a}' for m in mods for a, _ in ACCIONES]
        for rol, mods in ROL_MODULOS.items()
    }
    _sembrar(apps, matriz, rol_a_codigos)
    _borrar(apps, CODIGOS_0005)


def revertir(apps, schema_editor):
    matriz_codigos = [f'{m}.{a}' for m, _ in MODULOS for a, _ in ACCIONES]
    _borrar(apps, matriz_codigos)
    _sembrar(apps, PERMISOS_0005, ROL_PERMISOS_0005)


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0005_permisos_semilla'),
    ]

    operations = [
        migrations.RunPython(aplicar, revertir),
    ]
