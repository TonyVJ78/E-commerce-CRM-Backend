import logging

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .chatbot import ChatbotNoConfigurado, ChatbotNoDisponible, responder
from .serializers_chatbot import ChatbotSerializer


logger = logging.getLogger(__name__)


class ChatbotView(APIView):
    """POST /api/ia/chatbot/ — Asistente de recomendaciones de productos.

    Recibe el historial `{"mensajes": [{"rol", "contenido"}, ...]}` y devuelve
    `{"mensaje": <markdown>, "productos": [...], "sugerencias": [...]}`.
    Cada mensaje consume la API de Claude, por eso tiene un límite por usuario.
    """

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'chatbot'

    def post(self, request):
        serializer = ChatbotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            resultado = responder(serializer.como_mensajes_claude())
        except ChatbotNoConfigurado as exc:
            logger.error('Chatbot sin configurar: %s', exc)
            return Response(
                {'detail': 'El asistente no está disponible en este momento.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except ChatbotNoDisponible as exc:
            logger.warning('Chatbot no disponible: %s', exc.__cause__ or exc)
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(resultado)
