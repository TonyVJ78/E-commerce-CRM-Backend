from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('catalogo', '0005_remove_atributo_tienda_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='VarianteStockMovimiento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('previous_stock', models.IntegerField()),
                ('delta', models.IntegerField()),
                ('resulting_stock', models.IntegerField()),
                ('reason', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='ajustes_stock_catalogo',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('variante', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='stock_movimientos',
                    to='catalogo.variante',
                )),
            ],
            options={
                'db_table': 'variante_stock_movimiento',
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.AddConstraint(
            model_name='variantestockmovimiento',
            constraint=models.CheckConstraint(
                condition=~models.Q(('delta', 0)),
                name='stock_mov_delta_no_cero',
            ),
        ),
        migrations.AddConstraint(
            model_name='variantestockmovimiento',
            constraint=models.CheckConstraint(
                condition=models.Q(('previous_stock__gte', 0)),
                name='stock_mov_anterior_no_negativo',
            ),
        ),
        migrations.AddConstraint(
            model_name='variantestockmovimiento',
            constraint=models.CheckConstraint(
                condition=models.Q(('resulting_stock__gte', 0)),
                name='stock_mov_resultante_no_negativo',
            ),
        ),
    ]
