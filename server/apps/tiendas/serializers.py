"""
Serializers del módulo de Tiendas.
"""

from pathlib import Path
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.utils.text import slugify
from rest_framework import serializers

from .models import Tienda
from .services import delete_uploaded_logo, upload_store_logo


COLOR_HEX_ERROR = 'El color debe tener el formato hexadecimal #RRGGBB.'
SLUG_IN_USE_ERROR = 'Este slug ya está en uso.'


class AlertaStockSerializer(serializers.Serializer):
    producto_id = serializers.IntegerField()
    producto_nombre = serializers.CharField()
    variante_id = serializers.IntegerField()
    variante_nombre = serializers.CharField()
    sku = serializers.CharField()
    stock = serializers.IntegerField()
    stock_minimo = serializers.IntegerField()


class VentaDiaSerializer(serializers.Serializer):
    fecha = serializers.DateField()
    cantidad = serializers.IntegerField()


class TiendaPanelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tienda
        fields = ['id', 'nombre', 'slug', 'descripcion', 'logo_url', 'color_primario', 'activa']


class PanelTiendaSerializer(serializers.Serializer):
    tienda = TiendaPanelSerializer()
    tienda_id = serializers.IntegerField()
    tienda_nombre = serializers.CharField()
    total_productos = serializers.IntegerField()
    productos_activos = serializers.IntegerField()
    total_pedidos = serializers.IntegerField()
    pedidos_pendientes = serializers.IntegerField()
    ingresos_totales = serializers.DecimalField(max_digits=20, decimal_places=2)
    productos_bajo_stock = serializers.IntegerField()
    alertas_stock = AlertaStockSerializer(many=True)
    ventas_semana = VentaDiaSerializer(many=True)


def normalize_store_slug(value):
    """Normaliza un slug con la misma regla usada por ``Tienda.save``."""
    normalized = slugify(value or '')
    if not normalized:
        raise serializers.ValidationError('Ingresa un slug válido.')
    if len(normalized) > 100:
        raise serializers.ValidationError('El slug no puede superar los 100 caracteres.')
    return normalized


def validate_unique_store_slug(value, instance=None):
    queryset = Tienda.objects.filter(slug=value)
    if instance is not None:
        queryset = queryset.exclude(pk=instance.pk)
    if queryset.exists():
        raise serializers.ValidationError(SLUG_IN_USE_ERROR)
    return value


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
        """Normaliza el slug y excluye la propia tienda al comprobar unicidad."""
        if not value:
            return value
        normalized = normalize_store_slug(value)
        return validate_unique_store_slug(normalized, self.instance)

    def validate_color_primario(self, value):
        if not value or len(value) != 7 or value[0] != '#':
            raise serializers.ValidationError(COLOR_HEX_ERROR)
        try:
            int(value[1:], 16)
        except ValueError as exc:
            raise serializers.ValidationError(COLOR_HEX_ERROR) from exc
        return value.upper()


class TiendaIdentidadSerializer(serializers.ModelSerializer):
    """Campos editables de CU-13; nunca expone ni acepta ``propietario``."""

    slug = serializers.CharField(max_length=100, required=False, allow_blank=False)
    color_primario = serializers.RegexField(
        regex=r'^#[0-9A-Fa-f]{6}$',
        required=False,
        error_messages={'invalid': COLOR_HEX_ERROR},
    )
    logo = serializers.FileField(write_only=True, required=False, allow_null=False)

    class Meta:
        model = Tienda
        fields = ['id', 'nombre', 'slug', 'logo_url', 'color_primario', 'logo']
        read_only_fields = ['id', 'nombre', 'logo_url']

    def validate_slug(self, value):
        normalized = normalize_store_slug(value)
        return validate_unique_store_slug(normalized, self.instance)

    def validate_color_primario(self, value):
        return value.upper()

    def validate_logo(self, value):
        # La validación definitiva inspecciona firma, MIME y tamaño en backend.
        from apps.catalogo.services import validate_product_image

        if Path(value.name).suffix.lower() not in {'.jpg', '.jpeg', '.png', '.webp'}:
            raise serializers.ValidationError('El logotipo debe ser JPEG, PNG o WebP.')
        try:
            validate_product_image(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return value

    def update(self, instance, validated_data):
        logo = validated_data.pop('logo', None)
        uploaded_logo = None

        if logo is not None:
            uploaded_logo = upload_store_logo(logo, instance.pk)
            validated_data['logo_url'] = uploaded_logo['url']

        try:
            return super().update(instance, validated_data)
        except IntegrityError as exc:
            if uploaded_logo:
                delete_uploaded_logo(uploaded_logo.get('public_id', ''))
            raise serializers.ValidationError({'slug': [SLUG_IN_USE_ERROR]}) from exc
        except Exception:
            if uploaded_logo:
                delete_uploaded_logo(uploaded_logo.get('public_id', ''))
            raise
