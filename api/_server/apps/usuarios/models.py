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
    """Registro de cada intento de inicio de sesión (exitoso o fallido)."""
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name='bitacora_accesos',
        null=True,
        blank=True,
        help_text='NULL si el intento fue con un email que no existe.',
    )
    email_intento = models.EmailField(
        'email del intento',
        blank=True,
        default='',
        help_text='Email tal como se envió en el intento de login.',
    )
    exitoso = models.BooleanField('inicio de sesión exitoso', default=True)
    motivo = models.CharField(
        'motivo del rechazo',
        max_length=100,
        blank=True,
        default='',
        help_text='Solo se completa cuando exitoso=False.',
    )
    fecha = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField()
    dispositivo = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        db_table = 'bitacora_acceso'
        verbose_name = 'Bitácora de acceso'
        verbose_name_plural = 'Bitácoras de acceso'
        ordering = ['-fecha']
        indexes = [
            models.Index(fields=['-fecha'], name='bitacora_fecha_idx'),
            models.Index(fields=['usuario', '-fecha'], name='bitacora_usuario_fecha_idx'),
            models.Index(fields=['exitoso', '-fecha'], name='bitacora_exitoso_fecha_idx'),
        ]

    def __str__(self):
        quien = self.usuario.email if self.usuario else (self.email_intento or 'desconocido')
        estado = 'OK' if self.exitoso else 'FALLIDO'
        return f'{quien} - {estado} - {self.fecha}'


class Permiso(models.Model):
    """Permiso del sistema para control de acceso granular."""
    codigo = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=100)

    class Meta:
        db_table = 'permiso'
        verbose_name = 'Permiso'
        verbose_name_plural = 'Permisos'

    def __str__(self):
        return f'{self.codigo} - {self.nombre}'


class RolPermiso(models.Model):
    """Tabla intermedia explícita entre Rol y Permiso."""
    rol = models.ForeignKey(
        Rol,
        on_delete=models.CASCADE,
        related_name='roles_permisos',
    )
    permiso = models.ForeignKey(
        Permiso,
        on_delete=models.CASCADE,
        related_name='permisos_roles',
    )

    class Meta:
        db_table = 'rol_permiso'
        verbose_name = 'Rol Permiso'
        verbose_name_plural = 'Roles Permisos'
        unique_together = ('rol', 'permiso')

    def __str__(self):
        return f'{self.rol.nombre} - {self.permiso.codigo}'


class LogAuditoria(models.Model):
    """Registro de auditoría de cambios en tablas (solo rol administrador)."""
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name='logs_auditoria',
        null=True,
        blank=True,
    )
    tabla_afectada = models.CharField(max_length=50)
    registro_id = models.IntegerField()
    accion = models.CharField(max_length=20)
    datos_anteriores = models.JSONField(null=True, blank=True)
    datos_nuevos = models.JSONField(null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'log_auditoria'
        verbose_name = 'Log de Auditoría'
        verbose_name_plural = 'Logs de Auditoría'
        ordering = ['-fecha']
        indexes = [
            models.Index(fields=['-fecha'], name='logaud_fecha_idx'),
            models.Index(fields=['tabla_afectada', 'accion'], name='logaud_tabla_accion_idx'),
            models.Index(fields=['usuario', '-fecha'], name='logaud_usuario_fecha_idx'),
        ]

    def __str__(self):
        return f'{self.accion} en {self.tabla_afectada} (#{self.registro_id}) - {self.fecha}'

