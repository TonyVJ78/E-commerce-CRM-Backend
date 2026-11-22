"""
Serializers de CU-35: endpoints de Machine Learning.

Expone los resultados de predicción y los registros de entrenamiento sin
revelar datos comerciales sensibles de otras tiendas.
"""

from rest_framework import serializers

from .models import (
    EntrenamientoModelo,
    PrediccionCompra,
    PrediccionVenta,
    RiesgoAbandono,
)


class PrediccionVentaSerializer(serializers.ModelSerializer):
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)

    class Meta:
        model = PrediccionVenta
        fields = [
            'id',
            'tienda',
            'tienda_nombre',
            'periodo_inicio',
            'periodo_fin',
            'horizonte_dias',
            'valor_previsto',
            'mae',
            'rmse',
            'fecha_entrenamiento',
            'version_modelo',
        ]
        read_only_fields = fields


class RiesgoAbandonoSerializer(serializers.ModelSerializer):
    cliente_email = serializers.CharField(source='cliente.email', read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)

    class Meta:
        model = RiesgoAbandono
        fields = [
            'id',
            'cliente',
            'cliente_email',
            'tienda',
            'tienda_nombre',
            'probabilidad_abandono',
            'nivel_riesgo',
            'fecha_scoring',
            'version_modelo',
        ]
        read_only_fields = fields


class PrediccionCompraSerializer(serializers.ModelSerializer):
    cliente_email = serializers.CharField(source='cliente.email', read_only=True)
    tienda_nombre = serializers.CharField(source='tienda.nombre', read_only=True)

    class Meta:
        model = PrediccionCompra
        fields = [
            'id',
            'cliente',
            'cliente_email',
            'tienda',
            'tienda_nombre',
            'probabilidad_compra',
            'horizonte_dias',
            'fecha_prediccion',
            'version_modelo',
        ]
        read_only_fields = fields


class PrediccionCompraInputSerializer(serializers.Serializer):
    tienda_id = serializers.IntegerField(min_value=1, required=True)
    cliente_id = serializers.IntegerField(min_value=1, required=False)
    horizonte_dias = serializers.IntegerField(default=7, min_value=1, max_value=90)


class EntrenamientoModeloSerializer(serializers.ModelSerializer):
    usuario_email = serializers.CharField(source='usuario_ejecutor.email', read_only=True)

    class Meta:
        model = EntrenamientoModelo
        fields = [
            'id',
            'tipo_modelo',
            'estado',
            'metricas',
            'fecha_inicio',
            'fecha_fin',
            'usuario_email',
        ]
        read_only_fields = fields


# --- Serializers de entrada para los servicios ---

class PronosticarVentasInputSerializer(serializers.Serializer):
    tienda_id = serializers.IntegerField(min_value=1, required=True)
    horizonte_dias = serializers.IntegerField(default=7, min_value=1, max_value=90)


class RiesgoAbandonoInputSerializer(serializers.Serializer):
    tienda_id = serializers.IntegerField(min_value=1, required=True)
    cliente_id = serializers.IntegerField(min_value=1, required=False)
    dias_umbral_abandono = serializers.IntegerField(default=90, min_value=1, max_value=365)


class PredecirCompraInputSerializer(serializers.Serializer):
    tienda_id = serializers.IntegerField(min_value=1, required=True)
    cliente_id = serializers.IntegerField(min_value=1, required=False)
    horizonte_dias = serializers.IntegerField(default=7, min_value=1, max_value=90)


class EntrenarModeloInputSerializer(serializers.Serializer):
    tipo_modelo = serializers.ChoiceField(
        choices=['ventas', 'abandono', 'compras'],
        required=True,
    )
    tienda_id = serializers.IntegerField(min_value=1, required=False)


class PronosticarVentasInputSerializer(serializers.Serializer):
    tienda_id = serializers.IntegerField(min_value=1, required=True)
    horizonte_dias = serializers.IntegerField(default=7, min_value=1, max_value=90)
