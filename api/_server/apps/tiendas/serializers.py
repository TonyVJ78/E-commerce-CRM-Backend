"""
Serializers del módulo de Tiendas.
"""

from rest_framework import serializers

from .models import Tienda


class TiendaSerializer(serializers.ModelSerializer):
    """Serializer para crear y listar tiendas."""
    propietario_email = serializers.EmailField(source='propietario.email', read_only=True)

    class Meta:
        model = Tienda
        fields = [
            'id', 'propietario', 'propietario_email', 'nombre', 'slug',
            'logo_url', 'color_primario', 'descripcion', 'fecha_creacion', 'activa',
        ]
        read_only_fields = ['id', 'propietario', 'propietario_email', 'fecha_creacion']
        extra_kwargs = {
            'slug': {'required': False, 'allow_blank': True},
            'logo_url': {'required': False, 'allow_blank': True},
            'descripcion': {'required': False, 'allow_blank': True},
        }

    def validate_slug(self, value):
        """Validar unicidad del slug solo si fue proporcionado."""
        if value and Tienda.objects.filter(slug=value).exists():
            raise serializers.ValidationError('Este slug ya está en uso.')
        return value
