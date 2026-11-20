from rest_framework import serializers

from .satisfaccion import MINIMO_RESENAS_RANKING


class FiltroSatisfaccionSerializer(serializers.Serializer):
    desde = serializers.DateField(required=False)
    hasta = serializers.DateField(required=False)
    min_resenas = serializers.IntegerField(
        required=False, min_value=1, max_value=50, default=MINIMO_RESENAS_RANKING,
    )

    def validate(self, datos):
        desde, hasta = datos.get('desde'), datos.get('hasta')
        if desde and hasta and desde > hasta:
            raise serializers.ValidationError({'desde': 'Debe ser anterior o igual a hasta.'})
        return datos
