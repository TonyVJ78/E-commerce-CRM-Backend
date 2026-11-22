import json
from decimal import Decimal

from django.core.exceptions import ValidationError as ModelValidationError
from django.db import transaction
from rest_framework import serializers
from apps.finanzas.bloqueo import bloquear_cotizacion

from apps.finanzas.tipo_cambio import tipo_cambio_vigente
from apps.finanzas.brl import contexto_brl, visualizar_brl
from apps.tiendas.models import Tienda

from .models import Categoria, Producto, Variante, VarianteStockMovimiento
from .services import precio_bob_desde_usd, precio_efectivo

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
    try:
        return precio_bob_desde_usd(precio_usd, cotizacion.usd_bob)
    except ModelValidationError as exc:
        raise serializers.ValidationError({'precio_usd': exc.messages})


class SoloPreciosBobUsdMixin:
    def to_internal_value(self, data):
        if hasattr(data, 'get') and ('precio_brl' in data or str(data.get('moneda_precio', '')).upper() == 'BRL'):
            raise serializers.ValidationError({'precio_brl': 'BRL solo es una equivalencia informativa del catálogo.'})
        return super().to_internal_value(data)


class VarianteInputSerializer(SoloPreciosBobUsdMixin, serializers.Serializer):
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


class ProductoCreateSerializer(SoloPreciosBobUsdMixin, serializers.Serializer):
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


class PrecioPrimeraVarianteField(serializers.DecimalField):
    def get_attribute(self, instance):
        variante = instance.variantes.first()
        return getattr(variante, self.field_name) if variante else None


class PrecioUsdPrimeraVarianteField(serializers.DecimalField):
    """Precio en dólares del producto: se lee y se edita sobre la primera variante, como `precio`."""

    def get_attribute(self, instance):
        variante = instance.variantes.first()
        return variante.precio_usd if variante else None


class ProductoSerializer(SoloPreciosBobUsdMixin, serializers.ModelSerializer):
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
    precio = PrecioPrimeraVarianteField(max_digits=12, decimal_places=2, min_value=0, required=False)
    precio_oferta = PrecioPrimeraVarianteField(max_digits=12, decimal_places=2, min_value=0, required=False, allow_null=True)
    variante_id = serializers.IntegerField(min_value=1, required=False, write_only=True)
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
            'precio_usd', 'precio_oferta', 'variante_id', 'costo_unitario',
        ]

        read_only_fields = ['tienda']

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
            raise serializers.ValidationError({'stock': 'El stock solo puede cambiarse mediante un ajuste de variante.'})
        if self.instance is not None:
            tienda = self.initial_data.get('tienda', self.instance.tienda_id)
            if str(tienda) != str(self.instance.tienda_id):
                raise serializers.ValidationError({'tienda': 'No se puede trasladar el producto a otra tienda.'})
            categoria = attrs.get('categoria')
            if categoria is not None and categoria.tienda_id != self.instance.tienda_id:
                raise serializers.ValidationError({'categoria_id': 'La categoría no pertenece a esta tienda.'})
            categoria_legacy = self.initial_data.get('categoria')
            if categoria_legacy is not None and not isinstance(categoria_legacy, (str, int)):
                raise serializers.ValidationError({'categoria': 'La categoría debe ser un identificador o un nombre.'})
            if type(categoria_legacy) is int:
                try:
                    attrs['categoria'] = Categoria.objects.get(pk=categoria_legacy, tienda_id=self.instance.tienda_id)
                except Categoria.DoesNotExist:
                    raise serializers.ValidationError({'categoria': 'La categoría no pertenece a esta tienda.'})
            if 'variante_id' in attrs and not self.instance.variantes.filter(pk=attrs['variante_id']).exists():
                raise serializers.ValidationError({'variante_id': 'La variante no pertenece a este producto y tienda.'})
        return attrs

    @transaction.atomic
    def update(self, instance, validated_data):
        with bloquear_cotizacion():
            variante_id = validated_data.pop('variante_id', None)
            qs = Variante.objects.select_for_update().filter(producto_id=instance.pk).order_by('pk')
            variante = qs.get(pk=variante_id) if variante_id is not None else qs.first()
            monetarios = {k: validated_data.pop(k) for k in ('precio', 'precio_usd', 'precio_oferta', 'costo_unitario') if k in validated_data}
            if monetarios and variante is None:
                raise serializers.ValidationError({'variante_id': 'El producto no tiene variantes para editar.'})
            categoria_legacy = self.initial_data.get('categoria')
            if isinstance(categoria_legacy, str) and categoria_legacy.strip():
                validated_data['categoria'] = Categoria.objects.get_or_create(tienda_id=instance.tienda_id, nombre=categoria_legacy.strip())[0]
            imagen_url = self.initial_data.get('imagen_url')
            if imagen_url:
                validated_data['imagenes'] = [{'url': imagen_url, 'public_id': 'pc-upload'}]
            if variante is not None:
                if 'precio_usd' in monetarios:
                    variante.precio_usd = monetarios['precio_usd']
                elif 'precio' in monetarios:
                    variante.precio_usd = None
                if variante.precio_usd is not None and ('precio' in monetarios or 'precio_usd' in monetarios):
                    variante.precio = _precio_bob_desde_usd(variante.precio_usd)
                elif 'precio' in monetarios:
                    variante.precio = monetarios['precio']
                if 'precio_oferta' in monetarios:
                    variante.precio_oferta = monetarios['precio_oferta']
                if 'costo_unitario' in monetarios:
                    variante.costo_unitario = monetarios['costo_unitario']
                if monetarios:
                    variante.save(update_fields=['precio', 'precio_usd', 'precio_oferta', 'costo_unitario'])
            instance = super().update(instance, validated_data)
            instance._prefetched_objects_cache = {}
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
    visualizacion_brl = serializers.SerializerMethodField()

    def get_visualizacion_brl(self, obj):
        return visualizar_brl(obj.precio, precio_efectivo(obj), contexto_brl(self.context))

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
            'visualizacion_brl',
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
    visualizacion_brl = serializers.SerializerMethodField()

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
            'visualizacion_brl',
        ]

    def _variante_base(self, obj):
        variantes = [v for v in obj.variantes.all() if v.activa]
        return min(variantes, key=precio_efectivo, default=None)

    def get_precio_base(self, obj):
        variante = self._variante_base(obj)
        return str(precio_efectivo(variante)) if variante else "0.00"

    def get_precio_base_usd(self, obj):
        variante = self._variante_base(obj)
        if variante is None or variante.precio_usd is None or variante.precio_oferta is not None:
            return None
        return str(variante.precio_usd)

    def get_visualizacion_brl(self, obj):
        variante = self._variante_base(obj)
        return visualizar_brl(variante.precio, precio_efectivo(variante), contexto_brl(self.context)) if variante else None

    def get_imagen_principal(self, obj):
        if obj.imagenes and len(obj.imagenes) > 0:
            first = obj.imagenes[0]
            if isinstance(first, dict):
                return first.get('url', '')
            return str(first)
        return ''

