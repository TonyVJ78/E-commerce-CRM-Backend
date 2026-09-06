import json

from rest_framework import serializers

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
    categoria_id = serializers.IntegerField(read_only=True)
    variantes = VarianteOutputSerializer(many=True, read_only=True)
    stock_total = serializers.SerializerMethodField()
    agotado = serializers.SerializerMethodField()
    en_stock = serializers.SerializerMethodField()

    class Meta:
        model = Producto
        fields = [
            'id', 'tienda', 'categoria_id', 'nombre', 'slug', 'descripcion',
            'etiquetas', 'imagenes', 'activo', 'creado', 'actualizado',
            'variantes', 'stock_total', 'agotado', 'en_stock',
        ]

    def _active_variants(self, obj):
        return [variante for variante in obj.variantes.all() if variante.activa]

    def get_stock_total(self, obj):
        return sum(variante.stock for variante in self._active_variants(obj))

    def get_agotado(self, obj):
        return not any(variante.stock > 0 for variante in self._active_variants(obj))

    def get_en_stock(self, obj):
        return not self.get_agotado(obj)
