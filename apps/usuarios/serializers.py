"""
Serializers del módulo de Usuarios.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import serializers

from .models import BitacoraAcceso, LogAuditoria, Permiso, Rol, RolPermiso

Usuario = get_user_model()

# Roles creados por la migración `0002_roles_semilla.py`. No se pueden renombrar
# ni eliminar desde la API porque hay lógica de negocio atada a estos nombres.
ROLES_SEMILLA = {'administrador', 'empresa', 'cliente'}


class RolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rol
        fields = ['id', 'nombre']


class PermisoSerializer(serializers.ModelSerializer):
    """Un permiso de la matriz. `modulo`/`accion` salen de partir `codigo` por el punto."""
    modulo = serializers.SerializerMethodField()
    accion = serializers.SerializerMethodField()

    class Meta:
        model = Permiso
        fields = ['id', 'codigo', 'nombre', 'modulo', 'accion']

    def get_modulo(self, obj):
        return obj.codigo.split('.', 1)[0] if '.' in obj.codigo else obj.codigo

    def get_accion(self, obj):
        return obj.codigo.split('.', 1)[1] if '.' in obj.codigo else ''


class RolConPermisosSerializer(serializers.ModelSerializer):
    """Rol con la lista de permisos que tiene asignados y si es un rol del sistema."""
    permisos = serializers.SerializerMethodField()
    es_semilla = serializers.SerializerMethodField()
    usuarios_count = serializers.SerializerMethodField()

    class Meta:
        model = Rol
        fields = ['id', 'nombre', 'permisos', 'es_semilla', 'usuarios_count']

    def get_permisos(self, obj):
        permisos = [rp.permiso for rp in obj.roles_permisos.select_related('permiso').all()]
        return PermisoSerializer(permisos, many=True).data

    def get_es_semilla(self, obj):
        return obj.nombre in ROLES_SEMILLA

    def get_usuarios_count(self, obj):
        return obj.usuarios.count()

    def validate_nombre(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('El nombre del rol es obligatorio.')
        qs = Rol.objects.filter(nombre__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('Ya existe un rol con ese nombre.')
        # No permitir renombrar un rol semilla ni "convertir" otro en semilla.
        if self.instance and self.instance.nombre in ROLES_SEMILLA and value != self.instance.nombre:
            raise serializers.ValidationError('Los roles del sistema no se pueden renombrar.')
        if not self.instance and value.lower() in ROLES_SEMILLA:
            raise serializers.ValidationError('Ese nombre está reservado por el sistema.')
        return value


class RolPermisosUpdateSerializer(serializers.Serializer):
    """Body de `PUT /api/roles/<pk>/permisos/`: reemplaza el set completo."""
    permisos = serializers.PrimaryKeyRelatedField(
        queryset=Permiso.objects.all(), many=True
    )


class UsuarioAdminSerializer(serializers.ModelSerializer):
    """Gestión de usuarios por el administrador (CU07): rol y estado."""
    rol = RolSerializer(read_only=True)
    rol_id = serializers.PrimaryKeyRelatedField(
        queryset=Rol.objects.all(), source='rol', write_only=True, required=False
    )

    class Meta:
        model = Usuario
        fields = [
            'id', 'email', 'first_name', 'last_name',
            'rol', 'rol_id', 'activo', 'is_active', 'fecha_registro',
        ]
        read_only_fields = ['id', 'email', 'first_name', 'last_name', 'fecha_registro']


class RegistroSerializer(serializers.ModelSerializer):
    """Serializer para registrar un nuevo usuario."""
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        style={'input_type': 'password'},
    )
    password_confirm = serializers.CharField(
        write_only=True,
        style={'input_type': 'password'},
    )
    rol_id = serializers.PrimaryKeyRelatedField(
        queryset=Rol.objects.all(),
        source='rol',
        required=False,
    )

    class Meta:
        model = Usuario
        fields = ['id', 'email', 'first_name', 'last_name', 'password', 'password_confirm', 'rol_id']

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password_confirm'):
            raise serializers.ValidationError({'password_confirm': 'Las contraseñas no coinciden.'})
        
        password = attrs['password']
        if len(password) < 8:
            raise serializers.ValidationError({'password': 'La contraseña debe tener al menos 8 caracteres.'})
        if not any(c.isalpha() for c in password):
            raise serializers.ValidationError({'password': 'La contraseña debe contener al menos una letra.'})
        if not any(c.isdigit() for c in password):
            raise serializers.ValidationError({'password': 'La contraseña debe contener al menos un número.'})
        if not any(not c.isalnum() for c in password):
            raise serializers.ValidationError({'password': 'La contraseña debe contener al menos un carácter especial.'})

        try:
            validate_password(password)
        except DjangoValidationError as e:
            raise serializers.ValidationError({'password': list(e.messages)})
        return attrs

    def create(self, validated_data):
        # Si no se especifica rol, asignar 'cliente' por defecto
        if 'rol' not in validated_data or validated_data['rol'] is None:
            validated_data['rol'] = Rol.objects.get(nombre='cliente')
        password = validated_data.pop('password')
        usuario = Usuario(**validated_data)
        usuario.set_password(password)
        usuario.save()
        return usuario


class LoginSerializer(serializers.Serializer):
    """Serializer para iniciar sesión."""
    email = serializers.EmailField()
    password = serializers.CharField(style={'input_type': 'password'})


class PerfilSerializer(serializers.ModelSerializer):
    """Serializer para ver y editar el perfil del usuario."""
    rol = RolSerializer(read_only=True)

    class Meta:
        model = Usuario
        fields = ['id', 'email', 'first_name', 'last_name', 'rol', 'fecha_registro', 'activo']
        read_only_fields = ['id', 'email', 'rol', 'fecha_registro', 'activo']


class BitacoraAccesoSerializer(serializers.ModelSerializer):
    """Serializer de solo lectura para la bitácora de accesos (CU07)."""
    usuario_email = serializers.SerializerMethodField()
    usuario_nombre = serializers.SerializerMethodField()

    class Meta:
        model = BitacoraAcceso
        fields = [
            'id', 'usuario', 'usuario_email', 'usuario_nombre', 'email_intento',
            'exitoso', 'motivo', 'fecha', 'ip', 'dispositivo',
        ]

    def get_usuario_email(self, obj):
        if obj.usuario:
            return obj.usuario.email
        return obj.email_intento or None

    def get_usuario_nombre(self, obj):
        if not obj.usuario:
            return obj.email_intento or None
        nombre = f'{obj.usuario.first_name} {obj.usuario.last_name}'.strip()
        return nombre or obj.usuario.email


class LogAuditoriaSerializer(serializers.ModelSerializer):
    """Serializer de solo lectura para el log de auditoría de cambios (CU07)."""
    usuario_email = serializers.SerializerMethodField()

    class Meta:
        model = LogAuditoria
        fields = [
            'id', 'usuario', 'usuario_email', 'tabla_afectada', 'registro_id',
            'accion', 'datos_anteriores', 'datos_nuevos', 'fecha',
        ]

    def get_usuario_email(self, obj):
        return obj.usuario.email if obj.usuario else None


class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer para solicitar recuperación de contraseña."""
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer para confirmar nueva contraseña con token."""
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(
        min_length=8,
        style={'input_type': 'password'},
    )
    new_password_confirm = serializers.CharField(
        style={'input_type': 'password'},
    )

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({'new_password_confirm': 'Las contraseñas no coinciden.'})

        new_password = attrs['new_password']
        if len(new_password) < 8:
            raise serializers.ValidationError({'new_password': 'La contraseña debe tener al menos 8 caracteres.'})
        if not any(c.isalpha() for c in new_password):
            raise serializers.ValidationError({'new_password': 'La contraseña debe contener al menos una letra.'})
        if not any(c.isdigit() for c in new_password):
            raise serializers.ValidationError({'new_password': 'La contraseña debe contener al menos un número.'})
        if not any(not c.isalnum() for c in new_password):
            raise serializers.ValidationError({'new_password': 'La contraseña debe contener al menos un carácter especial.'})

        try:
            uid = urlsafe_base64_decode(attrs['uid']).decode()
            user = Usuario.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, UnicodeDecodeError, Usuario.DoesNotExist):
            raise serializers.ValidationError({'uid': 'Enlace de recuperación inválido.'})

        if not default_token_generator.check_token(user, attrs['token']):
            raise serializers.ValidationError({'token': 'Token inválido o expirado.'})

        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as e:
            raise serializers.ValidationError({'new_password': list(e.messages)})

        attrs['user'] = user
        return attrs

    def save(self):
        user = self.validated_data['user']
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user
