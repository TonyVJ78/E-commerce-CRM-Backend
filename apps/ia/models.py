"""
Modelos del Módulo 7: Inteligencia Artificial.
3 tablas: evento_usuario, recomendacion, reporte_generado.
"""

from django.conf import settings
from django.db import models


class EventoUsuario(models.Model):
    """Eventos de navegación e interacción del usuario para entrenamiento/análisis de IA."""
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='eventos_ia',
    )
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='eventos_usuario',
    )
    producto = models.ForeignKey(
        'catalogo.Producto',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='eventos_usuario',
    )
    tipo_evento = models.CharField(max_length=30)
    fecha = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'evento_usuario'
        verbose_name = 'Evento de Usuario'
        verbose_name_plural = 'Eventos de Usuarios'
        ordering = ['-fecha']

    def __str__(self):
        return f'{self.tipo_evento} por {self.cliente.email if self.cliente else "Anónimo"} ({self.fecha})'


class Recomendacion(models.Model):
    """Recomendaciones personalizadas de productos generadas por el motor de IA."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='recomendaciones',
    )
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='recomendaciones',
    )
    producto = models.ForeignKey(
        'catalogo.Producto',
        on_delete=models.CASCADE,
        related_name='recomendaciones',
    )
    score = models.DecimalField(max_digits=5, decimal_places=4)
    fecha_generada = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'recomendacion'
        verbose_name = 'Recomendación'
        verbose_name_plural = 'Recomendaciones'
        ordering = ['-score', '-fecha_generada']

    def __str__(self):
        return f'Recomendación {self.producto.nombre} a {self.cliente.email} (Score: {self.score})'


class ReporteGenerado(models.Model):
    """Reportes predictivos, analíticos o ejecutivos generados por el sistema."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='reportes_generados',
    )
    generado_por_usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reportes_generados',
    )
    tipo_reporte = models.CharField(max_length=50)
    formato = models.CharField(max_length=10)
    fecha_generacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reporte_generado'
        verbose_name = 'Reporte Generado'
        verbose_name_plural = 'Reportes Generados'
        ordering = ['-fecha_generacion']

    def __str__(self):
        return f'{self.tipo_reporte} ({self.formato}) - {self.tienda.nombre} ({self.fecha_generacion})'
