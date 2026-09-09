import json

from rest_framework import serializers

from apps.tiendas.models import Tienda

from .models import Categoria, Producto, Variante


def _json_object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'La clave JSON repetida no es valida: {key}.')
        result[key] = value
    return result


def _parse_json_field(data, field_name):
    value = data.get(field_name)
    if not isinstance(value, str):
        return data
    try:
        parsed = json.loads(value, object_pairs_hook=_json_object_pairs)
    except (TypeError, ValueError) as exc:
        raise serializers.ValidationError({
            field_name: 'Debe contener JSON valido.'
        }) from exc
    data[field_name] = parsed
    return data


class VarianteInputSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=60)
    nombre = serializers.CharField(max_length=100, required=False, default='Unica')
    precio = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    precio_oferta = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
        required=False,
        allow_null=True,
    )
    stock = serializers.IntegerField(min_value=0)
    stock_minimo = serializers.IntegerField(min_value=0)
    atributos = serializers.JSONField(required=False, default=dict)
    activa = serializers.BooleanField(required=False, default=True)

    def validate_sku(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('El SKU es obligatorio.')
        return value

    def validate_nombre(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('El nombre de la variante es obligatorio.')
        return value

    def validate_atributos(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('Los atributos deben ser un objeto JSON.')
        if any(not isinstance(key, str) or not key.strip() for key in value):
            raise serializers.ValidationError('Las claves de atributos no pueden estar vacias.')
        return value


class ProductoCreateSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=150)
    descripcion = serializers.CharField()
    categoria_id = serializers.IntegerField(required=False, allow_null=True)
    etiquetas = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        default=list,
    )
    activo = serializers.BooleanField(required=False, default=True)
    variantes = VarianteInputSerializer(many=True, allow_empty=False)
    imagenes = serializers.ListField(
        child=serializers.FileField(),
        required=True,
        allow_empty=False,
    )

    def to_internal_value(self, data):
        data = data.copy()
        for field_name in ('variantes', 'etiquetas'):
            data = _parse_json_field(data, field_name)
        return super().to_internal_value(data)

    def validate_nombre(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('El nombre es obligatorio.')
        return value

    def validate_descripcion(self, value):
        if not value.strip():
            raise serializers.ValidationError('La descripcion es obligatoria.')
        return value

    def validate_etiquetas(self, value):
        normalized = []
        seen = set()
        for etiqueta in value:
            etiqueta = etiqueta.strip()
            if etiqueta and etiqueta not in seen:
                normalized.append(etiqueta)
                seen.add(etiqueta)
        return normalized

    def validate_categoria_id(self, value):
        if value is not None and not Categoria.objects.filter(
            pk=value,
            tienda=self.context['tienda'],
        ).exists():
            raise serializers.ValidationError('La categoria no pertenece a esta tienda.')
        return value

    def validate_variantes(self, value):
        seen_skus = set()
        for variante in value:
            normalized_sku = variante['sku'].casefold()
            if normalized_sku in seen_skus:
                raise serializers.ValidationError('Los SKU deben ser unicos dentro del producto.')
            seen_skus.add(normalized_sku)
        return value


class VarianteOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = Variante
        fields = [
            'id', 'sku', 'nombre', 'precio', 'precio_oferta', 'stock',
            'stock_minimo', 'atributos', 'activa',
        ]


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ['id', 'nombre', 'categoria_padre']


class ProductoSerializer(serializers.ModelSerializer):
    categoria_id = serializers.PrimaryKeyRelatedField(
        queryset=Categoria.objects.all(),
        source='categoria',
        required=False,
        allow_null=True
    )
    variantes = VarianteOutputSerializer(many=True, read_only=True)
    stock_total = serializers.SerializerMethodField()
    agotado = serializers.SerializerMethodField()
    en_stock = serializers.SerializerMethodField()
    precio = serializers.SerializerMethodField()
    stock = serializers.SerializerMethodField()
    imagen_url = serializers.SerializerMethodField()

    class Meta:
        model = Producto
        fields = [
            'id', 'tienda', 'categoria_id', 'nombre', 'slug', 'descripcion',
            'etiquetas', 'imagenes', 'imagen_url', 'activo', 'creado', 'actualizado',
            'variantes', 'stock_total', 'agotado', 'en_stock', 'precio', 'stock',
        ]

    def _active_variants(self, obj):
        return [variante for variante in obj.variantes.all() if variante.activa]

    def get_stock_total(self, obj):
        return sum(variante.stock for variante in self._active_variants(obj))

    def get_agotado(self, obj):
        return not any(variante.stock > 0 for variante in self._active_variants(obj))

    def get_en_stock(self, obj):
        return not self.get_agotado(obj)

    def get_precio(self, obj):
        v = obj.variantes.first()
        return str(v.precio) if v else "0.00"

    def get_stock(self, obj):
        v = obj.variantes.first()
        return v.stock if v else 0

    def get_imagen_url(self, obj):
        if obj.imagenes and len(obj.imagenes) > 0:
            first = obj.imagenes[0]
            if isinstance(first, dict):
                return first.get('url', '')
            return str(first)
        return ''

    def update(self, instance, validated_data):
        precio = self.initial_data.get('precio')
        stock = self.initial_data.get('stock')
        categoria_val = self.initial_data.get('categoria')

        if categoria_val:
            if isinstance(categoria_val, int):
                instance.categoria_id = categoria_val
            elif isinstance(categoria_val, str) and categoria_val.strip():
                cat_obj, _ = Categoria.objects.get_or_create(
                    tienda=instance.tienda,
                    nombre=categoria_val.strip()
                )
                instance.categoria = cat_obj

        imagen_url = self.initial_data.get('imagen_url')
        if imagen_url:
            instance.imagenes = [{'url': imagen_url, 'public_id': 'pc-upload'}]

        instance = super().update(instance, validated_data)

        if precio is not None or stock is not None:
            variante = instance.variantes.first()
            if variante:
                if precio is not None:
                    variante.precio = precio
                if stock is not None:
                    variante.stock = stock
                variante.save()

        return instance


# =========================================================================
# Serializers de Catálogo Público para Clientes (CU-11)
# =========================================================================

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
    """Datos de una variante para visualización en el catálogo público."""

    nombre_variante = serializers.CharField(source='nombre', read_only=True)
    precio_adicional = serializers.CharField(source='precio', read_only=True)
    sku_variante = serializers.CharField(source='sku', read_only=True)

    class Meta:
        model = Variante
        fields = [
            'id',
            'nombre',
            'nombre_variante',
            'sku',
            'sku_variante',
            'precio',
            'precio_adicional',
            'precio_oferta',
            'stock',
            'activa',
            'atributos',
        ]


class ProductoCatalogoSerializer(serializers.ModelSerializer):
    """Producto con variantes, tienda, categoría e imágenes enriquecidas."""

    variantes = VarianteCatalogoSerializer(many=True, read_only=True)
    tienda_id = serializers.IntegerField(source='tienda.id', read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)
    tienda_slug = serializers.CharField(source='tienda.slug', read_only=True)
    categoria_id = serializers.IntegerField(source='categoria.id', read_only=True, default=None)
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True, default='')
    precio_base = serializers.SerializerMethodField()
    imagen_principal = serializers.SerializerMethodField()

    class Meta:
        model = Producto
        fields = [
            'id',
            'nombre',
            'slug',
            'descripcion',
            'imagenes',
            'imagen_principal',
            'tienda_id',
            'tienda_nombre',
            'tienda_slug',
            'categoria_id',
            'categoria_nombre',
            'precio_base',
            'variantes',
        ]

    def get_precio_base(self, obj):
        variantes = [v for v in obj.variantes.all() if v.activa]
        if variantes:
            return str(min(v.precio for v in variantes))
        return "0.00"

    def get_imagen_principal(self, obj):
        if obj.imagenes and len(obj.imagenes) > 0:
            first = obj.imagenes[0]
            if isinstance(first, dict):
                return first.get('url', '')
            return str(first)
        return ''

