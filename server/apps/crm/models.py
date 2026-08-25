"""
Modelos del Módulo 5: CRM: Gestión de Clientes.
5 tablas: segmento, ficha_cliente, interaccion_cliente, lista_deseos, item_lista_deseos.
"""

from django.conf import settings
from django.db import models


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
