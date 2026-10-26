"""
Modelos del Módulo 6: CRM: Marketing y Fidelización.
4 tablas: campana, cupon, cupon_uso, notificacion_enviada.
"""

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class Campana(models.Model):
    """Campaña de marketing y promociones de la tienda."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='campanas',
    )
    segmento_objetivo = models.ForeignKey(
        'crm.Segmento',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='campanas',
    )
    tipo = models.CharField(max_length=40)
    nombre = models.CharField(max_length=100)
    mensaje = models.TextField(blank=True, default='')
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()

    class Meta:
        db_table = 'campana'
        verbose_name = 'Campaña'
        verbose_name_plural = 'Campañas'

    def __str__(self):
        return f'{self.nombre} ({self.tienda.nombre})'


class Cupon(models.Model):
    """Cupones de descuento asociados o no a una campaña."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='cupones',
    )
    campana = models.ForeignKey(
        Campana,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='cupones',
    )
    codigo = models.CharField(max_length=30)
    tipo_descuento = models.CharField(max_length=20)
    valor_descuento = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_expiracion = models.DateField()
    usos_maximos = models.IntegerField(default=1)
    activo = models.BooleanField(default=True)
    fecha_inicio = models.DateField(default=timezone.localdate)
    monto_minimo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    limite_por_cliente = models.PositiveIntegerField(default=1)
    segmento_objetivo = models.ForeignKey(
        'crm.Segmento', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cupones',
    )

    class Meta:
        db_table = 'cupon'
        verbose_name = 'Cupón'
        verbose_name_plural = 'Cupones'
        constraints = [models.UniqueConstraint(
            Lower('codigo'), models.F('tienda'), name='cupon_codigo_por_tienda_uniq',
        )]

    def __str__(self):
        return f'{self.codigo} - {self.tipo_descuento} {self.valor_descuento} ({self.tienda.nombre})'


class CuponUso(models.Model):
    """Registro de uso de un cupón en un pedido."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='usos_cupones',
    )
    cupon = models.ForeignKey(
        Cupon,
        on_delete=models.CASCADE,
        related_name='usos',
    )
    pedido = models.ForeignKey(
        'pedidos.Pedido',
        on_delete=models.CASCADE,
        related_name='usos_cupon',
    )
    fecha_uso = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cupon_uso'
        verbose_name = 'Uso de Cupón'
        verbose_name_plural = 'Usos de Cupones'
        ordering = ['-fecha_uso']

    def __str__(self):
        return f'Cupón {self.cupon.codigo} usado en Pedido #{self.pedido_id}'


class NotificacionEnviada(models.Model):
    """Historial de notificaciones enviadas a clientes (email, SMS, push, etc.)."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='notificaciones_enviadas',
    )
    campana = models.ForeignKey(
        Campana,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notificaciones',
    )
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notificaciones_recibidas',
    )
    titulo = models.CharField(max_length=150, default='')
    mensaje = models.TextField(default='')
    tipo = models.CharField(max_length=30, default='general')
    datos = models.JSONField(default=dict)
    leida = models.BooleanField(default=False)
    fecha_lectura = models.DateTimeField(null=True, blank=True)
    clave_evento = models.CharField(max_length=200, unique=True, null=True, blank=True)
    canal = models.CharField(max_length=20)
    fecha = models.DateTimeField(auto_now_add=True)
    estado_entrega = models.CharField(max_length=20)

    class Meta:
        db_table = 'notificacion_enviada'
        verbose_name = 'Notificación Enviada'
        verbose_name_plural = 'Notificaciones Enviadas'
        ordering = ['-fecha']

    def __str__(self):
        return f'{self.canal} a {self.cliente.email} ({self.estado_entrega}) - {self.fecha}'


class DispositivoPush(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='dispositivos_push')
    token = models.CharField(max_length=512, unique=True)
    plataforma = models.CharField(max_length=10)
    activo = models.BooleanField(default=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'dispositivo_push'

    def __str__(self):
        return f'Dispositivo {self.pk} ({self.plataforma})'
