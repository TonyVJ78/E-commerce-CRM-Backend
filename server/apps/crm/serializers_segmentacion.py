from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.crm.models import ReglaSegmentacion, SegmentoCliente
from apps.crm.serializers import UsuarioResumenSerializer


class ReglaSegmentacionSerializer(serializers.ModelSerializer):
    tienda_id = serializers.IntegerField(read_only=True)
    umbral_alto_valor = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('0.01'),
    )

    class Meta:
        model = ReglaSegmentacion
        fields = [
            'id',
            'tienda_id',
            'dias_inactividad',
            'min_compras_frecuente',
            'umbral_alto_valor',
            'fecha_actualizacion',
        ]
        read_only_fields = ['id', 'tienda_id', 'fecha_actualizacion']

    def validate_dias_inactividad(self, value):
        if value < 1:
            raise serializers.ValidationError('Debe ser mayor que cero.')
        return value

    def validate_min_compras_frecuente(self, value):
        if value < 1:
            raise serializers.ValidationError('Debe ser mayor que cero.')
        return value


class ClienteSegmentadoSerializer(serializers.ModelSerializer):
    cliente = UsuarioResumenSerializer(read_only=True)

    class Meta:
        model = SegmentoCliente
        fields = [
            'id',
            'cliente',
            'segmento',
            'total_compras',
            'monto_total_gastado',
            'ticket_promedio',
            'ultima_compra',
            'actualizado_en',
        ]


class CampanaSegmentoPayloadSerializer(serializers.Serializer):
    segmento = serializers.ChoiceField(choices=SegmentoCliente.SEGMENTO_CHOICES)
    nombre = serializers.CharField(max_length=100)
    mensaje = serializers.CharField(required=False, allow_blank=True, default='')
    descuento_porcentaje = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal('0'),
        max_value=Decimal('100'),
        required=False,
        default=Decimal('0'),
    )
    codigo_cupon = serializers.CharField(max_length=30, required=False, allow_blank=True, default='')
    fecha_expiracion = serializers.DateField(required=False)

    def validate(self, attrs):
        attrs['nombre'] = attrs['nombre'].strip()
        attrs['mensaje'] = attrs['mensaje'].strip()
        attrs['codigo_cupon'] = attrs['codigo_cupon'].strip()
        if not attrs['nombre']:
            raise serializers.ValidationError({'nombre': 'El nombre es obligatorio.'})
        if not attrs['mensaje'] and attrs['descuento_porcentaje'] <= 0:
            raise serializers.ValidationError(
                'Debes incluir un mensaje o un descuento mayor que cero.'
            )
        if attrs['codigo_cupon'] and attrs['descuento_porcentaje'] <= 0:
            raise serializers.ValidationError({
                'codigo_cupon': 'El cupón requiere un descuento mayor que cero.'
            })
        if '\r' in attrs['nombre'] or '\n' in attrs['nombre']:
            raise serializers.ValidationError({'nombre': 'No se permiten saltos de línea.'})
        return attrs

    def validate_fecha_expiracion(self, value):
        if value <= timezone.localdate():
            raise serializers.ValidationError('La fecha debe ser posterior a hoy.')
        return value
