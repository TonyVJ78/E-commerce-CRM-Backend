"""
Modelos de finanzas: gastos operativos de cada tienda y tipo de cambio oficial.
2 tablas: gasto_operativo, tipo_cambio.
"""

from django.conf import settings
from django.db import models


class GastoOperativo(models.Model):
    """Gasto de la tienda que no es costo de mercadería: se resta de la ganancia bruta para la neta."""

    class Categoria(models.TextChoices):
        ALQUILER = 'alquiler', 'Alquiler'
        SERVICIOS = 'servicios', 'Servicios básicos'
        SUELDOS = 'sueldos', 'Sueldos'
        MARKETING = 'marketing', 'Marketing'
        TRANSPORTE = 'transporte', 'Transporte y envíos'
        IMPUESTOS = 'impuestos', 'Impuestos'
        OTROS = 'otros', 'Otros'

    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='gastos_operativos',
    )
    categoria = models.CharField(max_length=20, choices=Categoria.choices)
    descripcion = models.CharField(max_length=200, blank=True, default='')
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    fecha = models.DateField()
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gastos_registrados',
    )
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'gasto_operativo'
        verbose_name = 'Gasto operativo'
        verbose_name_plural = 'Gastos operativos'
        ordering = ['-fecha', '-id']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(monto__gt=0),
                name='gasto_operativo_monto_positivo',
            ),
        ]

    def __str__(self):
        return f'{self.tienda.nombre} - {self.get_categoria_display()} Bs {self.monto} ({self.fecha})'


class TipoCambio(models.Model):
    """Cotización oficial del BCB vigente en una fecha: dólar y UFV expresados en bolivianos."""
    fecha = models.DateField(unique=True)
    usd_bob = models.DecimalField(max_digits=10, decimal_places=4)
    ufv_bob = models.DecimalField(max_digits=10, decimal_places=5, null=True, blank=True)
    fuente = models.CharField(max_length=100)
    obtenido_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tipo_cambio'
        verbose_name = 'Tipo de cambio'
        verbose_name_plural = 'Tipos de cambio'
        ordering = ['-fecha']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(usd_bob__gt=0),
                name='tipo_cambio_usd_positivo',
            ),
        ]

    def __str__(self):
        return f'{self.fecha}: 1 USD = Bs {self.usd_bob}'
