from rest_framework import serializers

from .models import ReporteGenerado
from .serializers_chatbot import ChatbotSerializer


class GenerarInformeSerializer(ChatbotSerializer):
    """Historial de la conversación de informes + tienda elegida (opcional).

    Reusa la validación y la conversión del chatbot: mismos límites de
    mensajes y la misma alternancia usuario/asistente que exige Claude.
    """

    tienda_id = serializers.IntegerField(required=False, allow_null=True)


class InformeResumenSerializer(serializers.ModelSerializer):
    """Fila del historial: sin la tabla, para que la lista sea liviana."""

    tienda_nombre = serializers.SerializerMethodField()
    total_filas = serializers.SerializerMethodField()

    class Meta:
        model = ReporteGenerado
        fields = ['id', 'titulo', 'pregunta', 'tienda', 'tienda_nombre', 'total_filas', 'fecha_generacion']

    def get_tienda_nombre(self, obj):
        return obj.tienda.nombre if obj.tienda else None

    def get_total_filas(self, obj):
        return (obj.datos or {}).get('total_filas', 0)


class InformeSerializer(InformeResumenSerializer):
    columnas = serializers.SerializerMethodField()
    filas = serializers.SerializerMethodField()
    truncado = serializers.SerializerMethodField()
    filtros = serializers.SerializerMethodField()

    class Meta(InformeResumenSerializer.Meta):
        fields = InformeResumenSerializer.Meta.fields + [
            'analisis', 'grafico', 'columnas', 'filas', 'truncado', 'filtros',
        ]

    def get_columnas(self, obj):
        return (obj.datos or {}).get('columnas', [])

    def get_filas(self, obj):
        return (obj.datos or {}).get('filas', [])

    def get_truncado(self, obj):
        return bool((obj.datos or {}).get('truncado'))

    def get_filtros(self, obj):
        return (obj.datos or {}).get('filtros', '')
