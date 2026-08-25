"""
Modelos del Módulo 3: Catálogo e Inventario.
9 tablas: categoria, producto, variante_producto, atributo, variante_atributo,
          imagen_producto, inventario, etiqueta, producto_etiqueta.
"""

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
        on_delete=models.CASCADE,
        related_name='productos',
        null=True,
        blank=True,
    )
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True, default='')
    precio_base = models.DecimalField(max_digits=10, decimal_places=2)
    sku = models.CharField(max_length=50, blank=True, default='')
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'producto'
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'

    def __str__(self):
        return f'{self.nombre} ({self.tienda.nombre})'


class VarianteProducto(models.Model):
    """Variante específica de un producto (talla, color, etc.)."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='variantes_producto',
    )
    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name='variantes',
    )
    nombre_variante = models.CharField(max_length=100)
    precio_adicional = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    sku_variante = models.CharField(max_length=50, blank=True, default='')

    class Meta:
        db_table = 'variante_producto'
        verbose_name = 'Variante de Producto'
        verbose_name_plural = 'Variantes de Productos'

    def __str__(self):
        return f'{self.producto.nombre} - {self.nombre_variante}'


class Atributo(models.Model):
    """Definición de atributos de producto (ej. Color, Talla, Material)."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='atributos',
    )
    nombre = models.CharField(max_length=50)

    class Meta:
        db_table = 'atributo'
        verbose_name = 'Atributo'
        verbose_name_plural = 'Atributos'

    def __str__(self):
        return f'{self.tienda.nombre} - {self.nombre}'


class VarianteAtributo(models.Model):
    """Tabla intermedia explícita que asigna un valor a una variante para un atributo."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='variantes_atributos',
    )
    variante = models.ForeignKey(
        VarianteProducto,
        on_delete=models.CASCADE,
        related_name='variantes_atributos',
    )
    atributo = models.ForeignKey(
        Atributo,
        on_delete=models.CASCADE,
        related_name='variantes_atributos',
    )
    valor = models.CharField(max_length=50)

    class Meta:
        db_table = 'variante_atributo'
        verbose_name = 'Variante Atributo'
        verbose_name_plural = 'Variantes Atributos'

    def __str__(self):
        return f'{self.variante} -> {self.atributo.nombre}: {self.valor}'


class ImagenProducto(models.Model):
    """Imágenes asociadas a un producto."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='imagenes_producto',
    )
    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name='imagenes',
    )
    url = models.CharField(max_length=255)
    orden = models.IntegerField(default=0)

    class Meta:
        db_table = 'imagen_producto'
        verbose_name = 'Imagen de Producto'
        verbose_name_plural = 'Imágenes de Productos'
        ordering = ['orden']

    def __str__(self):
        return f'Imagen #{self.orden} de {self.producto.nombre}'


class Inventario(models.Model):
    """Control de existencias de cada variante de producto."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='inventarios',
    )
    variante = models.ForeignKey(
        VarianteProducto,
        on_delete=models.CASCADE,
        related_name='inventarios',
    )
    stock = models.IntegerField(default=0)
    umbral_minimo = models.IntegerField(default=5)

    class Meta:
        db_table = 'inventario'
        verbose_name = 'Inventario'
        verbose_name_plural = 'Inventarios'

    def __str__(self):
        return f'Stock: {self.stock} (Min: {self.umbral_minimo}) - {self.variante}'


class Etiqueta(models.Model):
    """Etiquetas para clasificar y filtrar productos."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='etiquetas',
    )
    nombre = models.CharField(max_length=50)

    class Meta:
        db_table = 'etiqueta'
        verbose_name = 'Etiqueta'
        verbose_name_plural = 'Etiquetas'

    def __str__(self):
        return f'{self.tienda.nombre} - {self.nombre}'


class ProductoEtiqueta(models.Model):
    """Tabla intermedia explícita entre Producto y Etiqueta."""
    tienda = models.ForeignKey(
        'tiendas.Tienda',
        on_delete=models.CASCADE,
        related_name='productos_etiquetas',
    )
    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name='productos_etiquetas',
    )
    etiqueta = models.ForeignKey(
        Etiqueta,
        on_delete=models.CASCADE,
        related_name='productos_etiquetas',
    )

    class Meta:
        db_table = 'producto_etiqueta'
        verbose_name = 'Producto Etiqueta'
        verbose_name_plural = 'Productos Etiquetas'
        unique_together = ('producto', 'etiqueta')

    def __str__(self):
        return f'{self.producto.nombre} - {self.etiqueta.nombre}'
