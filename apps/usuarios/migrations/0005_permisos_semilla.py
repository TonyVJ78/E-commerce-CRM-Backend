"""
Data migration (CU07 — Gestionar roles y permisos):
Siembra el catálogo de permisos y su mapeo a los roles semilla.

No modifica el esquema: solo inserta filas en `permiso` y `rol_permiso`, igual
que `0002_roles_semilla.py` hace con `rol`. El mapeo replica exactamente el
comportamiento actual (control de acceso por nombre de rol), de modo que migrar
un endpoint a `TienePermiso('...')` no cambia quién puede acceder.
"""

from django.db import migrations

# codigo -> nombre legible
PERMISOS = [
    ('ver_bitacora', 'Ver bitácora de accesos y auditoría'),
    ('gestionar_accesos', 'Gestionar roles, permisos y usuarios'),
    ('ver_dashboard_admin', 'Ver panel de administración'),
    ('crear_tienda', 'Crear y administrar tiendas'),
    ('gestionar_catalogo', 'Gestionar catálogo de productos'),
    ('gestionar_pedidos', 'Gestionar pedidos y envíos'),
    ('ver_panel_vendedor', 'Ver panel del vendedor'),
]

# nombre de rol -> códigos de permiso asignados
ROL_PERMISOS = {
    'administrador': ['ver_bitacora', 'gestionar_accesos', 'ver_dashboard_admin'],
    'empresa': ['crear_tienda', 'gestionar_catalogo', 'gestionar_pedidos', 'ver_panel_vendedor'],
    'cliente': [],
}


def sembrar(apps, schema_editor):
    Rol = apps.get_model('usuarios', 'Rol')
    Permiso = apps.get_model('usuarios', 'Permiso')
    RolPermiso = apps.get_model('usuarios', 'RolPermiso')

    permisos_por_codigo = {}
    for codigo, nombre in PERMISOS:
        permiso, _ = Permiso.objects.get_or_create(
            codigo=codigo, defaults={'nombre': nombre}
        )
        permisos_por_codigo[codigo] = permiso

    for nombre_rol, codigos in ROL_PERMISOS.items():
        try:
            rol = Rol.objects.get(nombre=nombre_rol)
        except Rol.DoesNotExist:
            continue
        for codigo in codigos:
            RolPermiso.objects.get_or_create(
                rol=rol, permiso=permisos_por_codigo[codigo]
            )


def revertir(apps, schema_editor):
    Permiso = apps.get_model('usuarios', 'Permiso')
    RolPermiso = apps.get_model('usuarios', 'RolPermiso')
    codigos = [codigo for codigo, _ in PERMISOS]
    RolPermiso.objects.filter(permiso__codigo__in=codigos).delete()
    Permiso.objects.filter(codigo__in=codigos).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0004_bitacoraacceso_email_intento_bitacoraacceso_exitoso_and_more'),
    ]

    operations = [
        migrations.RunPython(sembrar, revertir),
    ]
