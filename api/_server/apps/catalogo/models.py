"""
Modelos del modulo de catalogo.
Las tablas principales son categoria, producto y variante.
"""

from django.contrib.postgres.fields import ArrayField
from django.db import models


class Categoria(models.Model):
    """Categoría de productos dentro de una tienda (soporta subcategorías)."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='categorias',
    )
    nombre = models.CharField(max_length=100)
    categoria_padre = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subcategorias',
    )

    class Meta:
        db_table = 'categoria'
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'

    def __str__(self):
        return f'{self.tienda.nombre} - {self.nombre}'


class Producto(models.Model):
    """Producto base ofrecido por una tienda."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='productos',
    )
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.SET_NULL,
        related_name='productos',
        null=True,
        blank=True,
    )
    nombre = models.CharField(max_length=150)
    slug = models.CharField(max_length=180, default='')
    descripcion = models.TextField(blank=True, default='')
    etiquetas = ArrayField(
        models.CharField(max_length=50),
        default=list,
        blank=True,
    )
    imagenes = models.JSONField(default=list, blank=True)
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'producto'
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'

    def __str__(self):
        return f'{self.nombre} ({self.tienda.nombre})'


class Variante(models.Model):
    """Variante específica de un producto (talla, color, etc.)."""
    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name='variantes',
    )
    nombre = models.CharField(max_length=100, default='Unica')
    sku = models.CharField(max_length=60)
    precio = models.DecimalField(max_digits=12, decimal_places=2)
    precio_oferta = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    stock = models.IntegerField(default=0)
    stock_minimo = models.IntegerField(default=5)
    atributos = models.JSONField(default=dict, blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        db_table = 'variante'
        verbose_name = 'Variante'
        verbose_name_plural = 'Variantes'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(precio__gte=0),
                name='variante_precio_no_negativo',
            ),
            models.CheckConstraint(
                condition=models.Q(precio_oferta__isnull=True) | models.Q(precio_oferta__gte=0),
                name='variante_precio_oferta_no_negativo',
            ),
            models.CheckConstraint(
                condition=models.Q(stock__gte=0),
                name='variante_stock_no_negativo',
            ),
            models.CheckConstraint(
                condition=models.Q(stock_minimo__gte=0),
                name='variante_stock_minimo_no_negativo',
            ),
            models.UniqueConstraint(
                fields=['producto', 'sku'],
                name='variante_producto_sku_unico',
            ),
        ]

    def __str__(self):
        return f'{self.producto.nombre} - {self.nombre}'
