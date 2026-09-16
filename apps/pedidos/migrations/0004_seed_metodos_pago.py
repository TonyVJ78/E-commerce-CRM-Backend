"""Métodos de pago semilla para el checkout (CU-19)."""

from django.db import migrations


NOMBRES = ['Efectivo', 'QR', 'Tarjeta (Stripe)']


def crear_metodos_pago(apps, schema_editor):
    MetodoPago = apps.get_model('pedidos', 'MetodoPago')
    for nombre in NOMBRES:
        MetodoPago.objects.get_or_create(nombre=nombre)


def eliminar_metodos_pago(apps, schema_editor):
    MetodoPago = apps.get_model('pedidos', 'MetodoPago')
    MetodoPago.objects.filter(nombre__in=NOMBRES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0003_triggers_negocio_kantu'),
    ]

    operations = [
        migrations.RunPython(crear_metodos_pago, eliminar_metodos_pago),
    ]
