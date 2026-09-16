# Generated for CU-14 - Ver recomendaciones personalizadas.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ia', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='eventousuario',
            name='termino_busqueda',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
        migrations.AlterField(
            model_name='eventousuario',
            name='tipo_evento',
            field=models.CharField(
                choices=[
                    ('VIEW', 'Vista de producto'),
                    ('CLICK', 'Clic en producto'),
                    ('SEARCH', 'Búsqueda'),
                    ('CART', 'Agregado al carrito'),
                ],
                max_length=30,
            ),
        ),
        migrations.AddIndex(
            model_name='eventousuario',
            index=models.Index(
                fields=['cliente', 'tienda', '-fecha'],
                name='evt_cli_tda_fecha_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='eventousuario',
            index=models.Index(
                fields=['cliente', 'tienda', 'tipo_evento'],
                name='evt_cli_tda_tipo_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='eventousuario',
            index=models.Index(
                fields=['producto', '-fecha'],
                name='evt_prod_fecha_idx',
            ),
        ),
    ]
