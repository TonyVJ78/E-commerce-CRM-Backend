"""
Modelos de persistencia para CU-35: Machine Learning (Pronóstico de ventas,
Riesgo de abandono y Predicción de compras).

Estos modelos registran los resultados de entrenamiento e inferencia. No
almacenan datos comerciales sensibles de clientes ni transacciones reales;
solo guardan métricas, probabilidades y metadatos de ejecución.
"""

from django.conf import settings
from django.db import models


class PrediccionVenta(models.Model):
    """Resultado de un pronóstico de ventas para una tienda y horizonte dado."""

    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='predicciones_venta',
        verbose_name='tienda',
    )
    periodo_inicio = models.DateField(verbose_name='periodo inicio')
    periodo_fin = models.DateField(verbose_name='periodo fin')
    horizonte_dias = models.PositiveIntegerField(
        default=7,
        verbose_name='horizonte en días',
    )
    valor_previsto = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name='valor previsto',
    )
    mae = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='error absoluto medio (MAE)',
    )
    rmse = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='raíz del error cuadrático medio (RMSE)',
    )
    fecha_entrenamiento = models.DateTimeField(auto_now_add=True)
    version_modelo = models.CharField(max_length=32, default='1.0.0')

    class Meta:
        db_table = 'ml_prediccion_venta'
        verbose_name = 'Pronóstico de ventas'
        verbose_name_plural = 'Pronósticos de ventas'
        ordering = ['-fecha_entrenamiento']

    def __str__(self):
        return f'Venta {self.tienda.nombre} +{self.horizonte_dias}d = {self.valor_previsto}'


class RiesgoAbandono(models.Model):
    """Resultado del scoring de riesgo de abandono de un cliente en una tienda."""

    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='riesgos_abandono',
        verbose_name='cliente',
    )
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='riesgos_abandono',
        verbose_name='tienda',
    )
    probabilidad_abandono = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        verbose_name='probabilidad de abandono',
    )
    nivel_riesgo = models.CharField(
        max_length=20,
        verbose_name='nivel de riesgo',
        help_text='bajo, medio, alto o crítico',
    )
    fecha_scoring = models.DateTimeField(auto_now_add=True)
    version_modelo = models.CharField(max_length=32, default='1.0.0')

    class Meta:
        db_table = 'ml_riesgo_abandono'
        verbose_name = 'Riesgo de abandono'
        verbose_name_plural = 'Riesgos de abandono'
        ordering = ['-probabilidad_abandono']

    def __str__(self):
        return f'{self.cliente.email} - {self.tienda.nombre} - {self.nivel_riesgo}'


class PrediccionCompra(models.Model):
    """Resultado de la predicción de próxima compra de un cliente en una tienda."""

    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='predicciones_compra',
        verbose_name='cliente',
    )
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='predicciones_compra',
        verbose_name='tienda',
    )
    probabilidad_compra = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        verbose_name='probabilidad de compra',
    )
    horizonte_dias = models.PositiveIntegerField(
        default=7,
        verbose_name='horizonte en días',
    )
    fecha_prediccion = models.DateTimeField(auto_now_add=True)
    version_modelo = models.CharField(max_length=32, default='1.0.0')

    class Meta:
        db_table = 'ml_prediccion_compra'
        verbose_name = 'Predicción de compra'
        verbose_name_plural = 'Predicciones de compra'
        ordering = ['-probabilidad_compra']

    def __str__(self):
        return f'{self.cliente.email} - {self.tienda.nombre} - {self.horizonte_dias}d'


class EntrenamientoModelo(models.Model):
    """Registro trazable de cada ejecución de entrenamiento de modelos de ML."""

    TIPO_VENTAS = 'ventas'
    TIPO_ABANDONO = 'abandono'
    TIPO_COMPRAS = 'compras'
    TIPOS_MODELOS = [
        (TIPO_VENTAS, 'Pronóstico de ventas'),
        (TIPO_ABANDONO, 'Riesgo de abandono'),
        (TIPO_COMPRAS, 'Predicción de compras'),
    ]

    ESTADO_COMPLETADO = 'completado'
    ESTADO_FALLIDO = 'fallido'
    ESTADO_INSUFICIENTE = 'insuficiente_datos'
    ESTADOS = [
        (ESTADO_COMPLETADO, 'Completado'),
        (ESTADO_FALLIDO, 'Fallido'),
        (ESTADO_INSUFICIENTE, 'Datos insuficientes'),
    ]

    tipo_modelo = models.CharField(
        max_length=20,
        choices=TIPOS_MODELOS,
        verbose_name='tipo de modelo',
    )
    estado = models.CharField(
        max_length=30,
        choices=ESTADOS,
        default=ESTADO_INSUFICIENTE,
        verbose_name='estado',
    )
    metricas = models.JSONField(default=dict, blank=True, verbose_name='métricas')
    fecha_inicio = models.DateTimeField(auto_now_add=True)
    fecha_fin = models.DateTimeField(null=True, blank=True)
    usuario_ejecutor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='entrenamientos_ml',
        verbose_name='usuario ejecutor',
    )

    class Meta:
        db_table = 'ml_entrenamiento_modelo'
        verbose_name = 'Entrenamiento de modelo'
        verbose_name_plural = 'Entrenamientos de modelos'
        ordering = ['-fecha_inicio']

    def __str__(self):
        return f'{self.tipo_modelo} - {self.estado} ({self.fecha_inicio})'
