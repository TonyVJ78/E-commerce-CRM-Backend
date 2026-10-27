from django.db import migrations, models
from django.db.models import F
from django.utils import timezone


def conservar_antiguedad(apps, schema_editor):
    Carrito = apps.get_model('pedidos', 'Carrito')
    Carrito.objects.using(schema_editor.connection.alias).update(ultima_actividad=F('fecha_creacion'))


class Migration(migrations.Migration):
    dependencies = [('pedidos', '0006_fix_stock_variant_transfer')]
    operations = [
        migrations.AddField(model_name='carrito', name='ultima_actividad',
                            field=models.DateTimeField(default=timezone.now)),
        migrations.RunPython(conservar_antiguedad, migrations.RunPython.noop),
    ]
