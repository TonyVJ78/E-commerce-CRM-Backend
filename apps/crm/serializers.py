"""
Serializadores REST para los módulos CU-26 (Soporte / Reclamos) y CU-27 (Carritos Abandonados).
"""

from rest_framework import serializers
from apps.crm.models import (
    TicketSoporte,
    MensajeTicket,
    CampanaCarrito,
    RegistroRecuperacionCarrito,
)
from apps.pedidos.models import Pedido, Carrito


class UsuarioResumenSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True)
    nombre = serializers.SerializerMethodField()

    def get_nombre(self, obj):
        full_name = f"{getattr(obj, 'first_name', '')} {getattr(obj, 'last_name', '')}".strip()
        return full_name or getattr(obj, 'email', '')


class MensajeTicketSerializer(serializers.ModelSerializer):
    autor = UsuarioResumenSerializer(read_only=True)

    class Meta:
        model = MensajeTicket
        fields = [
            'id',
            'ticket',
            'autor',
            'contenido',
            'archivo_adjunto',
            'fecha_envio',
        ]
        read_only_fields = ['id', 'ticket', 'autor', 'fecha_envio']


class TicketSoporteSerializer(serializers.ModelSerializer):
    cliente = UsuarioResumenSerializer(read_only=True)
    tienda_id = serializers.IntegerField(source='tienda.id', read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)
    pedido_codigo = serializers.SerializerMethodField()
    tipo_display = serializers.CharField(source='get_tipo_display', read_only=True)
    prioridad_display = serializers.CharField(source='get_prioridad_display', read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)
    mensajes = MensajeTicketSerializer(many=True, read_only=True)
    total_mensajes = serializers.SerializerMethodField()

    class Meta:
        model = TicketSoporte
        fields = [
            'id',
            'codigo_ticket',
            'cliente',
            'tienda_id',
            'tienda_nombre',
            'pedido',
            'pedido_codigo',
            'tipo',
            'tipo_display',
            'prioridad',
            'prioridad_display',
            'estado',
            'estado_display',
            'asunto',
            'descripcion',
            'fecha_creacion',
            'fecha_actualizacion',
            'fecha_resolucion',
            'mensajes',
            'total_mensajes',
        ]
        read_only_fields = [
            'id',
            'codigo_ticket',
            'cliente',
            'tienda_id',
            'tienda_nombre',
            'fecha_creacion',
            'fecha_actualizacion',
            'fecha_resolucion',
        ]

    def get_pedido_codigo(self, obj):
        if obj.pedido_id:
            return f"PED-{obj.pedido_id:05d}"
        return None

    def get_total_mensajes(self, obj):
        return obj.mensajes.count()


class CrearTicketSerializer(serializers.ModelSerializer):
    tienda_id = serializers.IntegerField(required=False, allow_null=True)
    pedido_id = serializers.IntegerField(required=False, allow_null=True)
    archivo_adjunto = serializers.URLField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = TicketSoporte
        fields = [
            'tienda_id',
            'pedido_id',
            'tipo',
            'prioridad',
            'asunto',
            'descripcion',
            'archivo_adjunto',
        ]

    def validate(self, attrs):
        pedido_id = attrs.get('pedido_id')
        tienda_id = attrs.get('tienda_id')
        user = self.context['request'].user

        if pedido_id:
            try:
                pedido = Pedido.objects.get(id=pedido_id, cliente=user)
                attrs['pedido_obj'] = pedido
                # Si viene pedido, la tienda se asigna automaticamente a la del pedido
                attrs['tienda_id'] = pedido.tienda_id
            except Pedido.DoesNotExist:
                raise serializers.ValidationError({
                    'pedido_id': 'El pedido especificado no existe o no pertenece a tu cuenta.'
                })
        elif not tienda_id:
            raise serializers.ValidationError({
                'tienda_id': 'Debes especificar una tienda o un pedido asociado.'
            })

        return attrs


class CrearMensajeTicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = MensajeTicket
        fields = ['contenido', 'archivo_adjunto']

    def validate_contenido(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError('El mensaje no puede estar vacio.')
        return value.strip()


class CampanaCarritoSerializer(serializers.ModelSerializer):
    tienda_id = serializers.IntegerField(source='tienda.id', read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)

    class Meta:
        model = CampanaCarrito
        fields = [
            'id',
            'tienda_id',
            'tienda_nombre',
            'activo',
            'horas_inactividad',
            'asunto_email',
            'mensaje_email',
            'descuento_porcentaje',
            'codigo_cupon',
            'fecha_actualizacion',
        ]
        read_only_fields = ['id', 'tienda_id', 'tienda_nombre', 'fecha_actualizacion']

    def validate_horas_inactividad(self, value):
        if value < 1 or value > 72:
            raise serializers.ValidationError('Las horas de inactividad deben estar entre 1 y 72 horas.')
        return value

    def validate_descuento_porcentaje(self, value):
        if value < 0 or value > 50:
            raise serializers.ValidationError('El porcentaje de descuento debe estar entre 0% y 50%.')
        return value


class RegistroRecuperacionCarritoSerializer(serializers.ModelSerializer):
    cliente = UsuarioResumenSerializer(read_only=True)
    pedido_id = serializers.IntegerField(source='pedido_resultante.id', read_only=True, allow_null=True)

    class Meta:
        model = RegistroRecuperacionCarrito
        fields = [
            'id',
            'campana',
            'carrito',
            'cliente',
            'fecha_envio',
            'recuperado',
            'pedido_id',
        ]
        read_only_fields = ['id', 'fecha_envio']
