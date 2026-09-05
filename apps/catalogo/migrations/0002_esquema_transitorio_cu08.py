from django.contrib.postgres.fields import ArrayField
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogo', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='producto',
            name='slug',
            field=models.CharField(default='', max_length=180),
        ),
        migrations.AddField(
            model_name='producto',
            name='etiquetas',
            field=ArrayField(
                base_field=models.CharField(max_length=50),
                default=list,
                blank=True,
                size=None,
            ),
        ),
        migrations.AddField(
            model_name='producto',
            name='imagenes',
            field=models.JSONField(default=list, blank=True),
        ),
        migrations.AddField(
            model_name='producto',
            name='creado',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name='producto',
            name='actualizado',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name='producto',
            name='categoria',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='productos',
                to='catalogo.categoria',
            ),
        ),
        migrations.AlterField(
            model_name='imagenproducto',
            name='producto',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='imagenes_legadas',
                to='catalogo.producto',
            ),
        ),
        migrations.RenameModel(
            old_name='VarianteProducto',
            new_name='Variante',
        ),
        migrations.AlterModelTable(
            name='variante',
            table='variante',
        ),
        migrations.AlterModelOptions(
            name='variante',
            options={
                'verbose_name': 'Variante',
                'verbose_name_plural': 'Variantes',
            },
        ),
        migrations.RenameField(
            model_name='variante',
            old_name='nombre_variante',
            new_name='nombre',
        ),
        migrations.RenameField(
            model_name='variante',
            old_name='sku_variante',
            new_name='sku',
        ),
        migrations.AlterField(
            model_name='variante',
            name='nombre',
            field=models.CharField(default='Unica', max_length=100),
        ),
        migrations.AlterField(
            model_name='variante',
            name='sku',
            field=models.CharField(blank=True, default='', max_length=60),
        ),
        migrations.AddField(
            model_name='variante',
            name='precio',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='variante',
            name='precio_oferta',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='variante',
            name='stock',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='variante',
            name='stock_minimo',
            field=models.IntegerField(default=5),
        ),
        migrations.AddField(
            model_name='variante',
            name='atributos',
            field=models.JSONField(default=dict, blank=True),
        ),
        migrations.AddField(
            model_name='variante',
            name='activa',
            field=models.BooleanField(default=True),
        ),
    ]
