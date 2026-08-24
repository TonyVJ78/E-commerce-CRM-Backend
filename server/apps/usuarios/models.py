"""
Modelos del módulo de Accesos y Usuarios.
Sprint 0: Usuario, Rol, BitacoraAcceso.
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class Rol(models.Model):
    """
    Rol del usuario en la plataforma.
    Datos semilla: administrador, empresa, cliente.
    """
    nombre = models.CharField(max_length=50, unique=True)

    class Meta:
        db_table = 'rol'
        verbose_name = 'Rol'
        verbose_name_plural = 'Roles'

    def __str__(self):
        return self.nombre


class UsuarioManager(BaseUserManager):
    """Manager custom para el modelo Usuario con email como identificador."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('El email es obligatorio.')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('activo', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser debe tener is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser debe tener is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class Usuario(AbstractUser):
    """
    Modelo de usuario custom.
    Usa email como campo de autenticación (USERNAME_FIELD).
    Incluye campos 'activo' y 'fecha_registro' según el diccionario de datos oficial,
    separados de is_active y date_joined de AbstractUser.
    """
    username = None  # Se elimina username, se usa email

    email = models.EmailField('correo electrónico', unique=True)
    rol = models.ForeignKey(
        Rol,
        on_delete=models.PROTECT,
        related_name='usuarios',
        null=True,
        blank=True,
    )
    fecha_registro = models.DateTimeField('fecha de registro', auto_now_add=True)
    activo = models.BooleanField('activo', default=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []  # email ya es USERNAME_FIELD, no se repite

    objects = UsuarioManager()

    class Meta:
        db_table = 'usuario'
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return self.email


class BitacoraAcceso(models.Model):
    """Registro de cada inicio de sesión exitoso."""
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name='bitacora_accesos',
    )
    fecha = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField()
    dispositivo = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        db_table = 'bitacora_acceso'
        verbose_name = 'Bitácora de acceso'
        verbose_name_plural = 'Bitácoras de acceso'
        ordering = ['-fecha']

    def __str__(self):
        return f'{self.usuario.email} - {self.fecha}'
