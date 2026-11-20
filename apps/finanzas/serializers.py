from decimal import Decimal

from rest_framework import serializers

from .models import GastoOperativo, TipoCambio


class TipoCambioSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoCambio
        fields = ['fecha', 'usd_bob', 'ufv_bob', 'fuente']


class GastoOperativoSerializer(serializers.ModelSerializer):
    categoria_etiqueta = serializers.CharField(source='get_categoria_display', read_only=True)
    monto = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))

    class Meta:
        model = GastoOperativo
        fields = [
            'id', 'tienda', 'categoria', 'categoria_etiqueta', 'descripcion',
            'monto', 'fecha', 'registrado_por', 'creado',
        ]
        read_only_fields = ['tienda', 'registrado_por', 'creado']


class GastoFiltroSerializer(serializers.Serializer):
    """Filtros de la lista y de los totales: se validan igual que un cuerpo de petición."""
    desde = serializers.DateField(required=False)
    hasta = serializers.DateField(required=False)
    categoria = serializers.ChoiceField(choices=GastoOperativo.Categoria.choices, required=False)

    def validate(self, attrs):
        if 'desde' in attrs and 'hasta' in attrs and attrs['desde'] > attrs['hasta']:
            raise serializers.ValidationError({'desde': 'La fecha inicial es posterior a la final.'})
        return attrs
