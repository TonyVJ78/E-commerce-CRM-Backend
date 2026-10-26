"""
Modelos del Módulo 5: CRM: Gestión de Clientes.
5 tablas: segmento, ficha_cliente, interaccion_cliente, lista_deseos, item_lista_deseos.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class Segmento(models.Model):
    """Segmentación de clientes definida por la tienda."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='segmentos',
    )
    nombre = models.CharField(max_length=50)
    criterio = models.CharField(max_length=150)

    class Meta:
        db_table = 'segmento'
        verbose_name = 'Segmento'
        verbose_name_plural = 'Segmentos'

    def __str__(self):
        return f'{self.tienda.nombre} - {self.nombre}'


class FichaCliente(models.Model):
    """Ficha centralizada de datos y comportamiento del cliente en una tienda."""
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='fichas_cliente',
    )
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='fichas_cliente',
    )
    segmento = models.ForeignKey(
        Segmento,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='fichas_cliente',
    )
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ficha_cliente'
        verbose_name = 'Ficha de Cliente'
        verbose_name_plural = 'Fichas de Clientes'
        unique_together = ('cliente', 'tienda')

    def __str__(self):
        return f'Ficha {self.cliente.email} ({self.tienda.nombre})'


class InteraccionCliente(models.Model):
    """Registro de consultas, tickets o contactos con el cliente."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='interacciones_cliente',
    )
    ficha_cliente = models.ForeignKey(
        FichaCliente,
        on_delete=models.CASCADE,
        related_name='interacciones',
    )
    tipo = models.CharField(max_length=30)
    mensaje = models.TextField()
    fecha = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=20)

    class Meta:
        db_table = 'interaccion_cliente'
        verbose_name = 'Interacción con Cliente'
        verbose_name_plural = 'Interacciones con Clientes'
        ordering = ['-fecha']

    def __str__(self):
        return f'{self.tipo} ({self.estado}) - {self.ficha_cliente}'


class ListaDeseos(models.Model):
    """Lista de deseos (Wishlist) de un cliente en una tienda."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='listas_deseos',
    )
    ficha_cliente = models.ForeignKey(
        FichaCliente,
        on_delete=models.CASCADE,
        related_name='listas_deseos',
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'lista_deseos'
        verbose_name = 'Lista de Deseos'
        verbose_name_plural = 'Listas de Deseos'

    def __str__(self):
        return f'Wishlist #{self.id} de {self.ficha_cliente}'


class ItemListaDeseos(models.Model):
    """Productos guardados dentro de una lista de deseos."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='items_lista_deseos',
    )
    lista_deseos = models.ForeignKey(
        ListaDeseos,
        on_delete=models.CASCADE,
        related_name='items',
    )
    producto = models.ForeignKey(
        'catalogo.Producto',
        on_delete=models.CASCADE,
        related_name='en_listas_deseos',
    )

    class Meta:
        db_table = 'item_lista_deseos'
        verbose_name = 'Ítem de Lista de Deseos'
        verbose_name_plural = 'Ítems de Listas de Deseos'
        unique_together = ('lista_deseos', 'producto')

    def __str__(self):
        return f'{self.producto.nombre} en Wishlist #{self.lista_deseos_id}'


# =============================================================================
# CU-26: GESTIÓN DE CONSULTAS Y RECLAMOS POSTVENTA (TICKETS DE SOPORTE)
# =============================================================================

class TicketSoporte(models.Model):
    """Ticket de soporte o reclamo de un cliente hacia una tienda."""
    TIPO_CHOICES = [
        ('consulta', 'Consulta General'),
        ('reclamo_producto', 'Defecto de Producto'),
        ('demora_envio', 'Demora en Envio'),
        ('devolucion', 'Devolucion'),
    ]

    PRIORIDAD_CHOICES = [
        ('baja', 'Baja'),
        ('media', 'Media'),
        ('alta', 'Alta'),
        ('urgente', 'Urgente'),
    ]

    ESTADO_CHOICES = [
        ('abierto', 'Abierto'),
        ('en_proceso', 'En Proceso'),
        ('resuelto', 'Resuelto'),
        ('cerrado', 'Cerrado'),
    ]

    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tickets_soporte',
    )
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='tickets_tienda',
    )
    pedido = models.ForeignKey(
        'pedidos.Pedido',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tickets_asociados',
    )
    codigo_ticket = models.CharField(max_length=30, unique=True, blank=True)
    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES, default='consulta')
    prioridad = models.CharField(max_length=20, choices=PRIORIDAD_CHOICES, default='media')
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='abierto')
    asunto = models.CharField(max_length=200)
    descripcion = models.TextField()
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    fecha_resolucion = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ticket_soporte'
        verbose_name = 'Ticket de Soporte'
        verbose_name_plural = 'Tickets de Soporte'
        ordering = ['-fecha_creacion']

    def save(self, *args, **kwargs):
        if not self.codigo_ticket:
            anio = timezone.now().year
            conteo = TicketSoporte.objects.filter(codigo_ticket__startswith=f'TCK-{anio}-').count() + 1
            codigo = f'TCK-{anio}-{conteo:04d}'
            while TicketSoporte.objects.filter(codigo_ticket=codigo).exists():
                conteo += 1
                codigo = f'TCK-{anio}-{conteo:04d}'
            self.codigo_ticket = codigo

        if self.estado in ('resuelto', 'cerrado') and not self.fecha_resolucion:
            self.fecha_resolucion = timezone.now()
        elif self.estado in ('abierto', 'en_proceso'):
            self.fecha_resolucion = None

        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.codigo_ticket} - {self.asunto} ({self.get_estado_display()})'


class MensajeTicket(models.Model):
    """Mensajes intercambiados en el hilo del ticket de soporte."""
    ticket = models.ForeignKey(
        TicketSoporte,
        on_delete=models.CASCADE,
        related_name='mensajes',
    )
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='mensajes_tickets',
    )
    contenido = models.TextField()
    archivo_adjunto = models.URLField(max_length=500, blank=True, null=True)
    fecha_envio = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'mensaje_ticket'
        verbose_name = 'Mensaje de Ticket'
        verbose_name_plural = 'Mensajes de Tickets'
        ordering = ['fecha_envio']

    def __str__(self):
        return f'Mensaje de {self.autor.email} en {self.ticket.codigo_ticket}'


# =============================================================================
# CU-27: CAMPAÑAS DE RECUPERACIÓN DE CARRITOS ABANDONADOS
# =============================================================================

class CampanaCarrito(models.Model):
    """Configuración de automatización de carritos abandonados por tienda multitenant."""
    tienda = models.OneToOneField(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='campana_carrito',
    )
    activo = models.BooleanField(default=False)
    horas_inactividad = models.PositiveIntegerField(default=2)
    asunto_email = models.CharField(
        max_length=200,
        default='Tienes productos esperando en tu carrito',
    )
    mensaje_email = models.TextField(
        default='Notamos que dejaste articulos seleccionados en Kantu Market. Completa tu pedido antes de que se agote el stock.',
    )
    descuento_porcentaje = models.PositiveIntegerField(default=0)
    codigo_cupon = models.CharField(max_length=50, blank=True, null=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'campana_carrito'
        verbose_name = 'Campaña de Carrito Abandonado'
        verbose_name_plural = 'Campañas de Carritos Abandonados'

    def __str__(self):
        return f'Campana Carrito ({self.tienda.nombre}) - {"Activa" if self.activo else "Inactiva"}'


class RegistroRecuperacionCarrito(models.Model):
    """Bitácora de notificaciones de recuperación enviadas a clientes y su conversión."""
    campana = models.ForeignKey(
        CampanaCarrito,
        on_delete=models.CASCADE,
        related_name='notificaciones_enviadas',
    )
    carrito = models.ForeignKey(
        'pedidos.Carrito',
        on_delete=models.CASCADE,
        related_name='registros_recuperacion',
    )
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='registros_recuperacion_carrito',
    )
    fecha_envio = models.DateTimeField(auto_now_add=True)
    recuperado = models.BooleanField(default=False)
    correo_enviado = models.BooleanField(default=True)
    pedido_resultante = models.ForeignKey(
        'pedidos.Pedido',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recuperado_de_carrito',
    )

    class Meta:
        db_table = 'registro_recuperacion_carrito'
        verbose_name = 'Registro de Recuperación de Carrito'
        verbose_name_plural = 'Registros de Recuperación de Carritos'
        ordering = ['-fecha_envio']

    def __str__(self):
        return f'Recuperacion Carrito #{self.carrito_id} para {self.cliente.email}'


class ReglaSegmentacion(models.Model):
    """Umbrales RFM configurables por tienda."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='reglas_segmentacion',
    )
    dias_inactividad = models.PositiveIntegerField(default=60)
    min_compras_frecuente = models.PositiveIntegerField(default=3)
    umbral_alto_valor = models.DecimalField(max_digits=12, decimal_places=2, default=1000)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'regla_segmentacion'
        constraints = [
            models.UniqueConstraint(fields=['tienda'], name='crm_regla_segmentacion_tienda_uniq'),
            models.CheckConstraint(
                condition=models.Q(dias_inactividad__gte=1),
                name='crm_regla_segmentacion_dias_pos',
            ),
            models.CheckConstraint(
                condition=models.Q(min_compras_frecuente__gte=1),
                name='crm_regla_segmentacion_compras_pos',
            ),
            models.CheckConstraint(
                condition=models.Q(umbral_alto_valor__gt=0),
                name='crm_regla_segmentacion_umbral_pos',
            ),
        ]


class SegmentoCliente(models.Model):
    """Métricas y segmento RFM de un cliente en una tienda."""

    ALTO_VALOR = 'ALTO_VALOR'
    FRECUENTE = 'FRECUENTE'
    INACTIVO = 'INACTIVO'
    NUEVO = 'NUEVO'
    SEGMENTO_CHOICES = [
        (ALTO_VALOR, 'Alto valor'),
        (FRECUENTE, 'Frecuente'),
        (INACTIVO, 'Inactivo'),
        (NUEVO, 'Nuevo'),
    ]

    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='segmentos_clientes',
    )
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='segmentos_tienda',
    )
    segmento = models.CharField(max_length=20, choices=SEGMENTO_CHOICES)
    total_compras = models.PositiveIntegerField(default=0)
    monto_total_gastado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ticket_promedio = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ultima_compra = models.DateTimeField(null=True, blank=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'segmento_cliente'
        constraints = [
            models.UniqueConstraint(
                fields=['tienda', 'cliente'],
                name='crm_segmento_cliente_tienda_cliente_uniq',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(total_compras__gte=0)
                    & models.Q(monto_total_gastado__gte=0)
                    & models.Q(ticket_promedio__gte=0)
                ),
                name='crm_segmento_cliente_metricas_nonneg',
            ),
        ]
        ordering = ['cliente__email']
