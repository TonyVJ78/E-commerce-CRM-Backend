import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0003_triggers_negocio_kantu'),
    ]

    operations = [
        migrations.AddField(
            model_name='historialestadopedido',
            name='observacion',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='resena',
            name='producto',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='resenas',
                to='catalogo.producto',
            ),
        ),
    ]