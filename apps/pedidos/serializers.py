"""Serializers del carrito requeridos por CU-11."""

from django.db import transaction
from rest_framework import serializers, status
from rest_framework.exceptions import APIException

from apps.catalogo.models import Variante
from apps.tiendas.models import Tienda

from .models import Carrito, ItemCarrito


class MultiplesCarritosConflict(APIException):
    """Conflicto cuando CU-11 no puede determinar un único carrito a utilizar."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        'Existen varios carritos para el cliente y la tienda indicada. '
        'No es posible seleccionar uno de forma automática.'
    )
    default_code = 'multiples_carritos'


class AgregarItemCarritoSerializer(serializers.Serializer):
    """Valida tenant y crea un ItemCarrito con cantidad fija igual a uno."""

    tienda_id = serializers.IntegerField()
    variante_id = serializers.IntegerField()

    def validate(self, attrs):
        tienda_id = attrs['tienda_id']
        variante_id = attrs['variante_id']

        try:
            tienda = Tienda.objects.get(pk=tienda_id)
        except Tienda.DoesNotExist:
            raise serializers.ValidationError(
                {'tienda_id': 'La tienda indicada no existe.'}
            )

        try:
            variante = Variante.objects.select_related('producto').get(
                pk=variante_id,
                producto__tienda_id=tienda_id,
            )
        except Variante.DoesNotExist:
            raise serializers.ValidationError({
                'variante_id': 'La variante no pertenece a la tienda indicada.'
            })

        attrs['tienda'] = tienda
        attrs['variante'] = variante
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        cliente = validated_data['cliente']
        tienda = validated_data['tienda']
        variante = validated_data['variante']

        carritos = list(
            Carrito.objects.select_for_update()
            .filter(cliente=cliente, tienda=tienda)
            .order_by('pk')[:2]
        )

        if len(carritos) > 1:
            raise MultiplesCarritosConflict()

        carrito = carritos[0] if carritos else Carrito.objects.create(
            cliente=cliente,
            tienda=tienda,
        )

        return ItemCarrito.objects.create(
            tienda=tienda,
            carrito=carrito,
            variante=variante,
            cantidad=1,
        )


class ItemCarritoCreadoSerializer(serializers.ModelSerializer):
    """Respuesta mínima de la operación de agregado al carrito."""

    carrito_id = serializers.IntegerField(read_only=True)
    tienda_id = serializers.IntegerField(read_only=True)
    variante_id = serializers.IntegerField(read_only=True)
    producto_id = serializers.IntegerField(source='variante.producto_id', read_only=True)

    class Meta:
        model = ItemCarrito
        fields = [
            'id',
            'carrito_id',
            'tienda_id',
            'variante_id',
            'producto_id',
            'cantidad',
        ]


class ItemCarritoDetalleSerializer(serializers.ModelSerializer):
    """Detalle completo del ítem del carrito para el frontend."""

    variante_id = serializers.IntegerField(source='variante.id', read_only=True)
    variante_nombre = serializers.CharField(source='variante.nombre', read_only=True)
    variante_sku = serializers.CharField(source='variante.sku', read_only=True)
    precio_unitario = serializers.DecimalField(source='variante.precio', max_digits=10, decimal_places=2, read_only=True)
    subtotal = serializers.SerializerMethodField()
    producto_id = serializers.IntegerField(source='variante.producto.id', read_only=True)
    producto_nombre = serializers.CharField(source='variante.producto.nombre', read_only=True)
    producto_imagen = serializers.SerializerMethodField()
    tienda_id = serializers.IntegerField(source='tienda.id', read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)
    stock_disponible = serializers.IntegerField(source='variante.stock', read_only=True)

    class Meta:
        model = ItemCarrito
        fields = [
            'id',
            'carrito_id',
            'tienda_id',
            'tienda_nombre',
            'producto_id',
            'producto_nombre',
            'producto_imagen',
            'variante_id',
            'variante_nombre',
            'variante_sku',
            'precio_unitario',
            'cantidad',
            'subtotal',
            'stock_disponible',
        ]

    def get_subtotal(self, obj):
        return str(obj.cantidad * obj.variante.precio)

    def get_producto_imagen(self, obj):
        imgs = obj.variante.producto.imagenes
        if imgs and len(imgs) > 0:
            first = imgs[0]
            if isinstance(first, dict):
                return first.get('url', '')
            return str(first)
        return ''


class CarritoDetalleSerializer(serializers.ModelSerializer):
    """Representación de un carrito con sus ítems y total."""

    items = ItemCarritoDetalleSerializer(many=True, read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)
    total = serializers.SerializerMethodField()
    cantidad_items = serializers.SerializerMethodField()

    class Meta:
        model = Carrito
        fields = [
            'id',
            'tienda_id',
            'tienda_nombre',
            'fecha_creacion',
            'items',
            'cantidad_items',
            'total',
        ]

    def get_total(self, obj):
        total = sum(item.cantidad * item.variante.precio for item in obj.items.all())
        return str(total)

    def get_cantidad_items(self, obj):
        return sum(item.cantidad for item in obj.items.all())

