"""
Modelos del Módulo 4: Comercio Electrónico y Ventas.
10 tablas: carrito, item_carrito, metodo_pago, pedido, item_pedido,
           historial_estado_pedido, pago, direccion_envio, envio, resena.
"""

from django.conf import settings
from django.db import models


class Carrito(models.Model):
    """Carrito de compras de un cliente en una tienda."""
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='carritos',
    )
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='carritos',
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'carrito'
        verbose_name = 'Carrito'
        verbose_name_plural = 'Carritos'

    def __str__(self):
        return f'Carrito #{self.id} de {self.cliente.email} ({self.tienda.nombre})'


class ItemCarrito(models.Model):
    """Ítems agregados a un carrito de compras."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='items_carrito',
    )
    carrito = models.ForeignKey(
        Carrito,
        on_delete=models.CASCADE,
        related_name='items',
    )
    variante = models.ForeignKey(
        'catalogo.VarianteProducto',
        on_delete=models.CASCADE,
        related_name='en_carritos',
    )
    cantidad = models.IntegerField(default=1)

    class Meta:
        db_table = 'item_carrito'
        verbose_name = 'Ítem de Carrito'
        verbose_name_plural = 'Ítems de Carrito'

    def __str__(self):
        return f'{self.cantidad}x {self.variante} (Carrito #{self.carrito_id})'


class MetodoPago(models.Model):
    """Métodos de pago soportados en la plataforma (QR, Tarjeta, etc.)."""
    nombre = models.CharField(max_length=50)

    class Meta:
        db_table = 'metodo_pago'
        verbose_name = 'Método de Pago'
        verbose_name_plural = 'Métodos de Pago'

    def __str__(self):
        return self.nombre


class Pedido(models.Model):
    """Pedido realizado por un cliente en una tienda."""
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pedidos',
    )
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='pedidos',
    )
    estado_actual = models.CharField(max_length=30, default='pendiente')
    fecha = models.DateTimeField(auto_now_add=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'pedido'
        verbose_name = 'Pedido'
        verbose_name_plural = 'Pedidos'
        ordering = ['-fecha']

    def __str__(self):
        return f'Pedido #{self.id} - {self.cliente.email} ({self.estado_actual})'


class ItemPedido(models.Model):
    """Línea de detalle de productos de un pedido."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='items_pedido',
    )
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name='items',
    )
    variante = models.ForeignKey(
        'catalogo.VarianteProducto',
        on_delete=models.CASCADE,
        related_name='items_pedido',
    )
    cantidad = models.IntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'item_pedido'
        verbose_name = 'Ítem de Pedido'
        verbose_name_plural = 'Ítems de Pedido'

    def __str__(self):
        return f'{self.cantidad}x {self.variante} (Pedido #{self.pedido_id})'


class HistorialEstadoPedido(models.Model):
    """Trazabilidad histórica de los cambios de estado de un pedido."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='historial_estados_pedidos',
    )
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name='historial_estados',
    )
    estado = models.CharField(max_length=30)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'historial_estado_pedido'
        verbose_name = 'Historial Estado de Pedido'
        verbose_name_plural = 'Historiales Estados de Pedido'
        ordering = ['-fecha']

    def __str__(self):
        return f'Pedido #{self.pedido_id} -> {self.estado} ({self.fecha})'


class Pago(models.Model):
    """Registro de transacción de pago asociada a un pedido."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='pagos',
    )
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name='pagos',
    )
    metodo_pago = models.ForeignKey(
        MetodoPago,
        on_delete=models.CASCADE,
        related_name='pagos',
    )
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(max_length=20, default='pendiente')
    fecha = models.DateTimeField(auto_now_add=True)
    referencia_transaccion = models.CharField(max_length=100, blank=True, default='')

    class Meta:
        db_table = 'pago'
        verbose_name = 'Pago'
        verbose_name_plural = 'Pagos'
        ordering = ['-fecha']

    def __str__(self):
        return f'Pago #{self.id} de Bs {self.monto} ({self.estado})'


class DireccionEnvio(models.Model):
    """Dirección de entrega guardada por un cliente en una tienda."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='direcciones_envio',
    )
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='direcciones_envio',
    )
    direccion = models.CharField(max_length=200)
    ciudad = models.CharField(max_length=100)
    referencia = models.CharField(max_length=200, blank=True, default='')
    es_predeterminada = models.BooleanField(default=False)

    class Meta:
        db_table = 'direccion_envio'
        verbose_name = 'Dirección de Envío'
        verbose_name_plural = 'Direcciones de Envío'

    def __str__(self):
        return f'{self.cliente.email} - {self.ciudad}: {self.direccion}'


class Envio(models.Model):
    """Registro de despacho y seguimiento de un pedido."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='envios',
    )
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name='envios',
    )
    direccion_envio = models.ForeignKey(
        DireccionEnvio,
        on_delete=models.CASCADE,
        related_name='envios',
    )
    transportista = models.CharField(max_length=50, blank=True, default='')
    numero_seguimiento = models.CharField(max_length=50, blank=True, default='')
    fecha_envio = models.DateTimeField(null=True, blank=True)
    fecha_entrega = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'envio'
        verbose_name = 'Envío'
        verbose_name_plural = 'Envíos'

    def __str__(self):
        return f'Envío Pedido #{self.pedido_id} - Tracking: {self.numero_seguimiento or "S/N"}'


class Resena(models.Model):
    """Reseña y calificación de un producto por un cliente."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='resenas',
    )
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='resenas',
    )
    producto = models.ForeignKey(
        'catalogo.Producto',
        on_delete=models.CASCADE,
        related_name='resenas',
    )
    calificacion = models.SmallIntegerField()
    comentario = models.TextField(blank=True, default='')
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'resena'
        verbose_name = 'Reseña'
        verbose_name_plural = 'Reseñas'
        ordering = ['-fecha']

    def __str__(self):
        return f'★{self.calificacion}/5 por {self.cliente.email} en {self.producto.nombre}'
