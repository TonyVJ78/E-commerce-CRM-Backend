"""
Modelo Tienda — Módulo de Gestión de Tiendas (Multitenant).
Sprint 0: Solo la tabla tienda con campos base.
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


class UsuarioTienda(models.Model):
    """Asociación de usuarios a una tienda con un rol interno."""
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='usuarios_tiendas',
    )
    tienda = models.ForeignKey(
        Tienda,
        on_delete=models.CASCADE,
        related_name='usuarios_tienda',
    )
    rol_interno = models.CharField(max_length=30)
    fecha_asignacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'usuario_tienda'
        verbose_name = 'Usuario Tienda'
        verbose_name_plural = 'Usuarios Tiendas'
        unique_together = ('usuario', 'tienda')

    def __str__(self):
        return f'{self.usuario} - {self.tienda.nombre} ({self.rol_interno})'


class DireccionTienda(models.Model):
    """Dirección física y datos de contacto de una tienda."""
    tienda = models.ForeignKey(
        Tienda,
        on_delete=models.CASCADE,
        related_name='direcciones',
    )
    direccion = models.CharField(max_length=200)
    ciudad = models.CharField(max_length=100)
    telefono = models.CharField(max_length=30, blank=True, default='')

    class Meta:
        db_table = 'direccion_tienda'
        verbose_name = 'Dirección de Tienda'
        verbose_name_plural = 'Direcciones de Tiendas'

    def __str__(self):
        return f'{self.tienda.nombre} - {self.ciudad}: {self.direccion}'

