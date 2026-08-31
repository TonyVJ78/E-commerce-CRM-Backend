"""Serializers del carrito requeridos por CU-11."""

from django.db import transaction
from rest_framework import serializers, status
from rest_framework.exceptions import APIException

from apps.catalogo.models import VarianteProducto
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
            variante = VarianteProducto.objects.select_related('producto').get(
                pk=variante_id,
                tienda_id=tienda_id,
                producto__tienda_id=tienda_id,
            )
        except VarianteProducto.DoesNotExist:
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

        # Decisión técnica temporal de CU-11, no regla de negocio documentada:
        # 0 carritos -> crear; 1 -> reutilizar; más de 1 -> HTTP 409.
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

        # El esquema actual admite variantes repetidas. CU-11 crea una fila nueva
        # y no busca, fusiona ni incrementa un ItemCarrito existente.
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
