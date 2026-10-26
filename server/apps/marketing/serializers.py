from decimal import Decimal
import re
from django.utils import timezone
from rest_framework import serializers
from apps.crm.models import Segmento
from .models import Cupon


class CuponSerializer(serializers.ModelSerializer):
    tienda_id = serializers.IntegerField(read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)
    segmento_id = serializers.PrimaryKeyRelatedField(source='segmento_objetivo', queryset=Segmento.objects.all(), allow_null=True, required=False)
    segmento_nombre = serializers.CharField(source='segmento_objetivo.nombre', read_only=True, allow_null=True)
    usos_realizados = serializers.SerializerMethodField()

    class Meta:
        model = Cupon
        fields = ['id', 'tienda_id', 'tienda_nombre', 'codigo', 'tipo_descuento', 'valor_descuento',
                  'activo', 'fecha_inicio', 'fecha_expiracion', 'monto_minimo', 'usos_maximos',
                  'limite_por_cliente', 'segmento_id', 'segmento_nombre', 'usos_realizados']
        extra_kwargs = {'usos_maximos': {'min_value': 1}, 'limite_por_cliente': {'min_value': 1},
                        'monto_minimo': {'min_value': 0}, 'valor_descuento': {'min_value': Decimal('0.01')}}

    def get_usos_realizados(self, obj):
        return obj.usos.count()

    def validate_codigo(self, value):
        value = value.strip().upper()
        if not re.fullmatch(r'[A-Z0-9_-]{3,30}', value):
            raise serializers.ValidationError('Usa entre 3 y 30 letras, números, guiones o guiones bajos.')
        qs = Cupon.objects.filter(tienda=self.context['tienda'], codigo__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('Ya existe ese código en esta tienda.')
        return value

    def validate(self, attrs):
        def value(key, default=None):
            return attrs.get(key, getattr(self.instance, key, default))
        tipo = value('tipo_descuento')
        if tipo not in ('porcentaje', 'monto_fijo'):
            raise serializers.ValidationError({'tipo_descuento': 'Elige porcentaje o monto_fijo.'})
        if tipo == 'porcentaje' and value('valor_descuento', 0) > 100:
            raise serializers.ValidationError({'valor_descuento': 'El porcentaje no puede superar 100.'})
        inicio = value('fecha_inicio', timezone.localdate())
        fin = value('fecha_expiracion')
        if fin and fin < inicio:
            raise serializers.ValidationError({'fecha_expiracion': 'La expiración debe ser igual o posterior al inicio.'})
        segmento = value('segmento_objetivo')
        if segmento and segmento.tienda_id != self.context['tienda'].id:
            raise serializers.ValidationError({'segmento_id': 'El segmento no pertenece a esta tienda.'})
        return attrs
