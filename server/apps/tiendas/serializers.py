"""
Serializers del módulo de Tiendas y Productos.
"""

from rest_framework import serializers

from .models import Tienda, Producto


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


class ProductoSerializer(serializers.ModelSerializer):
    """
    Serializer para el catálogo de productos (CU09: Editar y Eliminar Productos).
    """
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)

    class Meta:
        model = Producto
        fields = [
            'id', 'tienda', 'tienda_nombre', 'nombre', 'descripcion',
            'precio', 'stock', 'categoria', 'imagen_url', 'activo',
            'fecha_creacion', 'fecha_actualizacion'
        ]
        read_only_fields = ['id', 'fecha_creacion', 'fecha_actualizacion']

    def validate_precio(self, value):
        if value <= 0:
            raise serializers.ValidationError("El precio debe ser mayor a 0.")
        return value

    def validate_stock(self, value):
        if value < 0:
            raise serializers.ValidationError("El stock no puede ser negativo.")
        return value