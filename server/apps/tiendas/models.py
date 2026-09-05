"""
Modelo Tienda y Producto — Módulo de Gestión de Tiendas y Catálogo (Multitenant).
Sprint 1: CU09 Editar y Eliminar Productos.
"""

from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Tienda(models.Model):
    """
    Tienda de un tenant en la plataforma Kantu Market.
    Campos según diccionario de datos oficial (Sprint 0).
    """
    propietario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tiendas',
        verbose_name='propietario',
    )
    nombre = models.CharField(max_length=150)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    logo_url = models.URLField(max_length=255, blank=True, default='')
    color_primario = models.CharField(max_length=7, default='#C8102E')
    descripcion = models.TextField(blank=True, default='')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    activa = models.BooleanField(default=True)

    class Meta:
        db_table = 'tienda'
        verbose_name = 'Tienda'
        verbose_name_plural = 'Tiendas'
        ordering = ['-fecha_creacion']

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        """Auto-genera slug desde el nombre si no fue proporcionado."""
        if not self.slug:
            base_slug = slugify(self.nombre)
            slug = base_slug
            counter = 1
            while Tienda.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base_slug}-{counter}'
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


class Producto(models.Model):
    """
    Producto perteneciente al catálogo de una tienda (Tenant).
    Soporta baja lógica mediante el campo 'activo' para preservar integridad de órdenes.
    """
    tienda = models.ForeignKey(
        Tienda,
        on_delete=models.CASCADE,
        related_name='productos',
        verbose_name='tienda'
    )
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True, default='')
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    categoria = models.CharField(max_length=100, blank=True, default='')
    imagen_url = models.URLField(max_length=500, blank=True, default='')
    activo = models.BooleanField(default=True)  # Borrado lógico
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'producto'
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"{self.nombre} ({self.tienda.nombre})"