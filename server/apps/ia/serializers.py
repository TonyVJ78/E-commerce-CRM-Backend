"""Serializers de CU-14: recomendaciones e interacciones del cliente."""

from rest_framework import serializers

from apps.catalogo.models import Producto
from apps.tiendas.models import Tienda

from .models import EventoUsuario
from .services import MAX_RECOMMENDATION_LIMIT, registrar_interaccion


class RecomendacionQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(
        required=False,
        default=8,
        min_value=1,
        max_value=MAX_RECOMMENDATION_LIMIT,
    )


class InteraccionProductoSerializer(serializers.Serializer):
    ALLOWED_CLIENT_EVENTS = (
        EventoUsuario.TipoEvento.VIEW,
        EventoUsuario.TipoEvento.CLICK,
        EventoUsuario.TipoEvento.SEARCH,
    )

    tienda_id = serializers.PrimaryKeyRelatedField(
        source='tienda',
        queryset=Tienda.objects.filter(activa=True),
    )
    producto_id = serializers.PrimaryKeyRelatedField(
        source='producto',
        queryset=Producto.objects.filter(activo=True, tienda__activa=True),
        required=False,
        allow_null=True,
    )
    tipo_interaccion = serializers.ChoiceField(choices=ALLOWED_CLIENT_EVENTS)
    termino_busqueda = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=150,
        trim_whitespace=True,
    )

    def validate(self, attrs):
        tienda = attrs['tienda']
        producto = attrs.get('producto')
        tipo = attrs['tipo_interaccion']
        termino = attrs.get('termino_busqueda', '').strip()

        if producto is not None and producto.tienda_id != tienda.id:
            raise serializers.ValidationError({
                'producto_id': 'El producto no pertenece a la tienda indicada.'
            })

        if tipo == EventoUsuario.TipoEvento.SEARCH:
            if not termino:
                raise serializers.ValidationError({
                    'termino_busqueda': 'Debe indicar el término buscado.'
                })
            if producto is not None:
                raise serializers.ValidationError({
                    'producto_id': 'Una búsqueda no debe indicar un producto.'
                })
        elif producto is None:
            raise serializers.ValidationError({
                'producto_id': 'VIEW y CLICK requieren un producto.'
            })

        attrs['termino_busqueda'] = termino
        return attrs

    def create(self, validated_data):
        return registrar_interaccion(
            cliente=self.context['request'].user,
            tienda=validated_data['tienda'],
            producto=validated_data.get('producto'),
            tipo_evento=validated_data['tipo_interaccion'],
            termino_busqueda=validated_data.get('termino_busqueda', ''),
        )


class InteraccionRegistradaSerializer(serializers.ModelSerializer):
    tipo_interaccion = serializers.CharField(source='tipo_evento')

    class Meta:
        model = EventoUsuario
        fields = [
            'id',
            'tienda_id',
            'producto_id',
            'tipo_interaccion',
            'termino_busqueda',
            'fecha',
        ]
