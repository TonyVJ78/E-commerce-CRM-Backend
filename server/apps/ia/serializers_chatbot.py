from rest_framework import serializers


MAX_MENSAJES_HISTORIAL = 20
MAX_LARGO_MENSAJE = 2000


class MensajeChatSerializer(serializers.Serializer):
    rol = serializers.ChoiceField(choices=['usuario', 'asistente'])
    contenido = serializers.CharField(max_length=MAX_LARGO_MENSAJE, trim_whitespace=True)


class ChatbotSerializer(serializers.Serializer):
    """Historial de la conversaci├│n, del m├ís antiguo al m├ís reciente."""

    mensajes = MensajeChatSerializer(many=True, allow_empty=False)

    def validate_mensajes(self, mensajes):
        if mensajes[-1]['rol'] != 'usuario':
            raise serializers.ValidationError('El ├║ltimo mensaje debe ser del usuario.')
        return mensajes

    def como_mensajes_claude(self):
        """Convierte al formato de la API de Claude.

        Se queda con los ├║ltimos mensajes, descarta los del asistente que
        quedan al inicio (el saludo de bienvenida) y junta mensajes seguidos
        del mismo rol, porque la API exige que user y assistant se alternen.
        """
        recientes = self.validated_data['mensajes'][-MAX_MENSAJES_HISTORIAL:]
        while recientes and recientes[0]['rol'] != 'usuario':
            recientes = recientes[1:]

        resultado = []
        for mensaje in recientes:
            rol = 'user' if mensaje['rol'] == 'usuario' else 'assistant'
            if resultado and resultado[-1]['role'] == rol:
                resultado[-1]['content'] += '\n\n' + mensaje['contenido']
            else:
                resultado.append({'role': rol, 'content': mensaje['contenido']})
        return resultado
