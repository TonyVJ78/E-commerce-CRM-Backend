from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .informes_consultas import COMPARACIONES


DIAS_POR_DEFECTO = 30
MAX_DIAS = 366


class PanelSerializer(serializers.Serializer):
    """Filtros del panel de KPIs. Sin fechas: los últimos 30 días hasta hoy."""

    tienda = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    desde = serializers.DateField(required=False, allow_null=True)
    hasta = serializers.DateField(required=False, allow_null=True)
    comparar_con = serializers.ChoiceField(choices=[*COMPARACIONES, 'ninguno'], default='periodo_anterior')

    def validate(self, datos):
        hasta = datos.get('hasta') or timezone.localdate()
        desde = datos.get('desde') or hasta - timedelta(days=DIAS_POR_DEFECTO - 1)
        if desde > hasta:
            raise serializers.ValidationError({'hasta': 'La fecha final no puede ser anterior a la inicial.'})
        if (hasta - desde).days + 1 > MAX_DIAS:
            raise serializers.ValidationError({'desde': f'El periodo no puede pasar de {MAX_DIAS} días.'})
        return {**datos, 'desde': desde, 'hasta': hasta}


class InterpretarPanelSerializer(PanelSerializer):
    pregunta = serializers.CharField(required=False, allow_blank=True, max_length=500)
