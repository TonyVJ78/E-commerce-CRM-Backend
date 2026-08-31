"""Serializers mínimos del catálogo visible para clientes."""

from rest_framework import serializers

from apps.tiendas.models import Tienda

from .models import Producto, VarianteProducto


class TiendaCatalogoSerializer(serializers.ModelSerializer):
    """Datos públicos mínimos de una tienda para el catálogo."""

    class Meta:
        model = Tienda
        fields = [
            'id',
            'nombre',
            'slug',
            'logo_url',
            'color_primario',
            'descripcion',
        ]


class VarianteCatalogoSerializer(serializers.ModelSerializer):
    """Datos existentes de una variante que el cliente puede agregar."""

    class Meta:
        model = VarianteProducto
        fields = [
            'id',
            'nombre_variante',
            'precio_adicional',
            'sku_variante',
        ]


class ProductoCatalogoSerializer(serializers.ModelSerializer):
    """Producto con las variantes del mismo tenant precargadas por la vista."""

    variantes = VarianteCatalogoSerializer(many=True, read_only=True)

    class Meta:
        model = Producto
        fields = [
            'id',
            'nombre',
            'descripcion',
            'precio_base',
            'sku',
            'variantes',
        ]
