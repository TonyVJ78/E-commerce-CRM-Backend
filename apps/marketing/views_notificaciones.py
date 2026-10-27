from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.usuarios.permissions import IsCliente
from .models import DispositivoPush, NotificacionEnviada


class RegistroDispositivoSerializer(serializers.Serializer):
    token = serializers.CharField(min_length=20, max_length=512, write_only=True)
    plataforma = serializers.ChoiceField(choices=['android', 'ios'])
    activo = serializers.BooleanField(default=True)


class DispositivoView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsCliente]

    def post(self, request):
        serializer = RegistroDispositivoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            if data['activo']:
                DispositivoPush.objects.update_or_create(token=data['token'], defaults={
                    'usuario': request.user, 'plataforma': data['plataforma'], 'activo': True})
            else:
                DispositivoPush.objects.filter(usuario=request.user, token=data['token']).update(activo=False)
        return Response({'registrado': data['activo'], 'push_disponible': settings.FCM_ENABLED})


class BandejaView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsCliente]

    def get(self, request):
        qs = NotificacionEnviada.objects.filter(cliente=request.user).select_related('tienda')
        # Cursor pagination avoids dropping old notifications beyond the first page.
        antes = request.query_params.get('antes')
        if antes:
            try:
                qs = qs.filter(pk__lt=int(antes))
            except ValueError:
                raise serializers.ValidationError({'antes': 'Cursor inválido.'})
        rows = list(qs.order_by('-pk')[:51])
        siguiente = rows[49].pk if len(rows) > 50 else None
        return Response({'no_leidas': NotificacionEnviada.objects.filter(cliente=request.user, leida=False).count(),
            'siguiente': siguiente, 'notificaciones': [dict(id=n.pk, titulo=n.titulo, mensaje=n.mensaje,
                tipo=n.tipo, datos=n.datos, leida=n.leida, fecha=n.fecha.isoformat(),
                tienda_id=n.tienda_id, tienda_nombre=n.tienda.nombre) for n in rows[:50]]})


class LeerNotificacionView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsCliente]

    def patch(self, request, pk):
        obj = get_object_or_404(NotificacionEnviada, pk=pk, cliente=request.user)
        if not obj.leida:
            obj.leida = True
            obj.fecha_lectura = timezone.now()
            obj.save(update_fields=['leida', 'fecha_lectura'])
        return Response({'id': obj.pk, 'leida': True})
