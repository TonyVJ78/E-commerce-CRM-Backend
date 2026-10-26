"""
Data migration (CU-34 — Informes con IA):
agrega el módulo `informes` a la matriz de permisos.

- `informes.ver`      → abrir el historial y exportar a PDF/Excel.
- `informes.crear`    → pedir informes nuevos a la IA.
- `informes.eliminar` → borrar informes del historial.
- `informes.editar`   → sin uso por ahora; se siembra para que la grilla quede completa.

Se conceden a `administrador` y `empresa` (dueños y encargados de tienda). El
administrador puede quitarlos o dárselos a otros roles desde Roles y permisos.
"""

from django.db import migrations

ACCIONES = [('ver', 'Ver'), ('crear', 'Crear'), ('editar', 'Editar'), ('eliminar', 'Eliminar')]
ETIQUETA_MODULO = 'Informes con IA'
CODIGOS = [(f'informes.{a}', f'{etiqueta} · {ETIQUETA_MODULO}') for a, etiqueta in ACCIONES]
ROLES = ['administrador', 'empresa']


def aplicar(apps, schema_editor):
    Rol = apps.get_model('usuarios', 'Rol')
    Permiso = apps.get_model('usuarios', 'Permiso')
    RolPermiso = apps.get_model('usuarios', 'RolPermiso')

    permisos = [
        Permiso.objects.get_or_create(codigo=codigo, defaults={'nombre': nombre})[0]
        for codigo, nombre in CODIGOS
    ]
    for rol in Rol.objects.filter(nombre__in=ROLES):
        for permiso in permisos:
            RolPermiso.objects.get_or_create(rol=rol, permiso=permiso)


def revertir(apps, schema_editor):
    Permiso = apps.get_model('usuarios', 'Permiso')
    RolPermiso = apps.get_model('usuarios', 'RolPermiso')
    codigos = [codigo for codigo, _ in CODIGOS]
    RolPermiso.objects.filter(permiso__codigo__in=codigos).delete()
    Permiso.objects.filter(codigo__in=codigos).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0007_respaldo_base_datos'),
    ]

    operations = [
        migrations.RunPython(aplicar, revertir),
    ]
