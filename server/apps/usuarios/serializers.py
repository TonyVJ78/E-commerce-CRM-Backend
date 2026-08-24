"""
Serializers del módulo de Usuarios.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import serializers

from .models import Rol

Usuario = get_user_model()


class RolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rol
        fields = ['id', 'nombre']


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

        validate_password(password)
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


class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer para solicitar recuperación de contraseña."""
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer para confirmar nueva contraseña con token."""
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(min_length=8, style={'input_type': 'password'})
    new_password_confirm = serializers.CharField(style={'input_type': 'password'})

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({'new_password_confirm': 'Las contraseñas no coinciden.'})
        validate_password(attrs['new_password'])

        try:
            uid = urlsafe_base64_decode(attrs['uid']).decode()
            user = Usuario.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, Usuario.DoesNotExist):
            raise serializers.ValidationError({'uid': 'Enlace de recuperación inválido.'})

        if not default_token_generator.check_token(user, attrs['token']):
            raise serializers.ValidationError({'token': 'Token inválido o expirado.'})

        attrs['user'] = user
        return attrs

    def save(self):
        user = self.validated_data['user']
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user
