import json
from decimal import Decimal

from rest_framework import serializers

from apps.finanzas.tipo_cambio import tipo_cambio_vigente
from apps.tiendas.models import Tienda

from .models import Categoria, Producto, Variante, VarianteStockMovimiento
from .services import precio_bob_desde_usd

SIN_COTIZACION = 'No hay tipo de cambio oficial cargado; usa precio en Bs.'


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


def _precio_bob_desde_usd(precio_usd):
    cotizacion = tipo_cambio_vigente()
    if cotizacion is None:
        raise serializers.ValidationError({'precio_usd': SIN_COTIZACION})
    return precio_bob_desde_usd(precio_usd, cotizacion.usd_bob)


class VarianteInputSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=60)
    nombre = serializers.CharField(max_length=100, required=False, default='Unica')
    precio = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False)
    precio_usd = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('0.01'),
        required=False,
        allow_null=True,
    )
    precio_oferta = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
        required=False,
        allow_null=True,
    )
    costo_unitario = serializers.DecimalField(
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

    def validate(self, attrs):
        precio_usd = attrs.get('precio_usd')
        if precio_usd is not None:
            attrs['precio'] = _precio_bob_desde_usd(precio_usd)
        elif 'precio' not in attrs:
            raise serializers.ValidationError({'precio': 'Indica el precio en Bs o en dólares.'})
        return attrs


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
        # Parsed JSON lists must not remain in a QueryDict: DRF would treat them
        # as HTML form fields and lose nested variants. Preserve all uploaded files.
        if hasattr(data, 'getlist'):
            data = {key: data.getlist(key) if key == 'imagenes' else data.get(key) for key in data.keys()}
        else:
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
        tienda = self.context.get('tienda')
        for variante in value:
            if tienda and Variante.objects.filter(producto__tienda=tienda, sku__iexact=variante['sku']).exists():
                raise serializers.ValidationError('Ya existe ese SKU en esta tienda.')
            normalized_sku = variante['sku'].casefold()
            if normalized_sku in seen_skus:
                raise serializers.ValidationError('Los SKU deben ser unicos dentro del producto.')
            seen_skus.add(normalized_sku)
        return value


class VarianteOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = Variante
        fields = [
            'id', 'sku', 'nombre', 'precio', 'precio_usd', 'precio_oferta', 'costo_unitario',
            'stock', 'stock_minimo', 'atributos', 'activa',
        ]


class StockAdjustmentInputSerializer(serializers.Serializer):
    delta = serializers.IntegerField(
        min_value=-2_147_483_648,
        max_value=2_147_483_647,
        required=False,
    )
    nuevo_stock = serializers.IntegerField(
        min_value=0,
        max_value=2_147_483_647,
        required=False,
    )
    tipo_ajuste = serializers.ChoiceField(
        choices=['INGRESO', 'SALIDA', 'CORRECCION'],
        required=False,
        default='CORRECCION',
    )
    reason = serializers.CharField(max_length=255, trim_whitespace=True, allow_blank=False)

    def to_internal_value(self, data):
        if not hasattr(data, 'get'):
            raise serializers.ValidationError({
                'non_field_errors': 'Se esperaba un objeto JSON.'
            })
        delta = data.get('delta')
        nuevo_stock = data.get('nuevo_stock')

        if delta is not None and type(delta) is not int:
            raise serializers.ValidationError({
                'delta': 'Debe ser un entero JSON, no una cadena ni un número decimal.'
            })
        if nuevo_stock is not None and type(nuevo_stock) is not int:
            raise serializers.ValidationError({
                'nuevo_stock': 'Debe ser un entero JSON no negativo.'
            })
        return super().to_internal_value(data)

    def validate(self, attrs):
        delta = attrs.get('delta')
        nuevo_stock = attrs.get('nuevo_stock')

        if delta is None and nuevo_stock is None:
            raise serializers.ValidationError(
                'Debe proporcionar "delta" o "nuevo_stock".'
            )
        if delta is not None and nuevo_stock is not None:
            raise serializers.ValidationError(
                'No puede enviar "delta" y "nuevo_stock" simultáneamente.'
            )
        if delta is not None and delta == 0:
            raise serializers.ValidationError({'delta': 'El delta no puede ser cero.'})

        return attrs

    def validate_reason(self, value):
        if not value:
            raise serializers.ValidationError('La razón es obligatoria.')
        return value


class StockMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = VarianteStockMovimiento
        fields = [
            'id', 'variante', 'previous_stock', 'delta', 'resulting_stock',
            'actor', 'reason', 'created_at',
        ]
        read_only_fields = fields


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ['id', 'nombre', 'categoria_padre']


class PrecioUsdPrimeraVarianteField(serializers.DecimalField):
    """Precio en dólares del producto: se lee y se edita sobre la primera variante, como `precio`."""

    def get_attribute(self, instance):
        variante = instance.variantes.first()
        return variante.precio_usd if variante else None


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
    precio_usd = PrecioUsdPrimeraVarianteField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('0.01'),
        required=False,
        allow_null=True,
    )
    # Se edita sobre la primera variante, igual que `precio`; al leerse viaja dentro de `variantes`.
    costo_unitario = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
        required=False,
        allow_null=True,
        write_only=True,
    )

    class Meta:
        model = Producto
        fields = [
            'id', 'tienda', 'categoria_id', 'nombre', 'slug', 'descripcion',
            'etiquetas', 'imagenes', 'imagen_url', 'activo', 'creado', 'actualizado',
            'variantes', 'stock_total', 'agotado', 'en_stock', 'precio', 'stock',
            'precio_usd', 'costo_unitario',
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

    def validate(self, attrs):
        if 'stock' in self.initial_data:
            raise serializers.ValidationError({
                'stock': 'El stock solo puede cambiarse mediante un ajuste de variante.'
            })
        return attrs

    def update(self, instance, validated_data):
        precio = self.initial_data.get('precio')
        cambia_precio_usd = 'precio_usd' in validated_data
        precio_usd = validated_data.pop('precio_usd', None)
        cambia_costo = 'costo_unitario' in validated_data
        costo_unitario = validated_data.pop('costo_unitario', None)
        categoria_val = self.initial_data.get('categoria')

        precio_desde_usd = _precio_bob_desde_usd(precio_usd) if precio_usd is not None else None

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

        if precio is not None or cambia_precio_usd or cambia_costo:
            variante = instance.variantes.first()
            if variante:
                if cambia_precio_usd:
                    variante.precio_usd = precio_usd
                elif precio is not None:
                    # Un precio en Bs sin `precio_usd` saca al producto de dólares: si no,
                    # la próxima cotización lo sobrescribiría.
                    variante.precio_usd = None
                if precio_desde_usd is not None:
                    variante.precio = precio_desde_usd
                elif precio is not None:
                    variante.precio = precio
                if cambia_costo:
                    variante.costo_unitario = costo_unitario
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
            'precio_usd',
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
    precio_base_usd = serializers.SerializerMethodField()
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
            'precio_base_usd',
            'variantes',
        ]

    def _variante_base(self, obj):
        variantes = [v for v in obj.variantes.all() if v.activa]
        return min(variantes, key=lambda v: v.precio, default=None)

    def get_precio_base(self, obj):
        variante = self._variante_base(obj)
        return str(variante.precio) if variante else "0.00"

    def get_precio_base_usd(self, obj):
        variante = self._variante_base(obj)
        if variante is None or variante.precio_usd is None:
            return None
        return str(variante.precio_usd)

    def get_imagen_principal(self, obj):
        if obj.imagenes and len(obj.imagenes) > 0:
            first = obj.imagenes[0]
            if isinstance(first, dict):
                return first.get('url', '')
            return str(first)
        return ''

