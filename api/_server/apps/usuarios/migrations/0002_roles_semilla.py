"""
Data migration: Crear roles semilla (administrador, empresa, cliente).
Esta migración se ejecuta automáticamente después de crear las tablas.
La dependencia se configurará después de ejecutar makemigrations.
"""

from django.db import migrations


def crear_roles_semilla(apps, schema_editor):
    Rol = apps.get_model('usuarios', 'Rol')
    roles = ['administrador', 'empresa', 'cliente']
    for nombre in roles:
        Rol.objects.get_or_create(nombre=nombre)


def revertir_roles(apps, schema_editor):
    Rol = apps.get_model('usuarios', 'Rol')
    Rol.objects.filter(nombre__in=['administrador', 'empresa', 'cliente']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(crear_roles_semilla, revertir_roles),
    ]
