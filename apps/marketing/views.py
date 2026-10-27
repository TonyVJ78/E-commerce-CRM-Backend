from django.db import transaction, IntegrityError
from django.db.models import Count, F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.crm.models import Segmento
from apps.pedidos.models import Carrito
from apps.tiendas.models import Tienda
from apps.usuarios.permissions import IsEmpresa, IsCliente
from apps.usuarios.audit import registrar_auditoria, ACCION_CREAR, ACCION_ACTUALIZAR
from .cupones import cotizar_carritos, es_destinatario, json_cotizacion
from .notificaciones import notificar_cupon
from .models import Cupon
from .serializers import CuponSerializer


class CuponesTiendaView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsEmpresa]

    def get_tienda(self, request, tienda_id):
        return get_object_or_404(Tienda, pk=tienda_id, propietario=request.user)

    def get(self, request, tienda_id):
        tienda = self.get_tienda(request, tienda_id)
        cupones = tienda.cupones.select_related('tienda', 'segmento_objetivo').order_by('-id')
        return Response({'cupones': CuponSerializer(cupones, many=True).data,
                         'segmentos': list(Segmento.objects.filter(tienda=tienda).values('id', 'nombre'))})

    def post(self, request, tienda_id):
        tienda = self.get_tienda(request, tienda_id)
        serializer = CuponSerializer(data=request.data, context={'tienda': tienda})
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                Tienda.objects.select_for_update().get(pk=tienda.id)
                cupon = serializer.save(tienda=tienda)
                notificar_cupon(cupon)
        except IntegrityError:
            raise ValidationError({'codigo': 'Ya existe ese código en esta tienda.'})
        registrar_auditoria(request, ACCION_CREAR, tabla='cupon', registro_id=cupon.id,
                            datos_nuevos={'codigo': cupon.codigo, 'tienda_id': tienda.id})
        return Response(CuponSerializer(cupon).data, status=status.HTTP_201_CREATED)


class CuponTiendaDetalleView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsEmpresa]
    def patch(self, request, tienda_id, pk):
        tienda = get_object_or_404(Tienda, pk=tienda_id, propietario=request.user)
        cupon = get_object_or_404(Cupon, pk=pk, tienda=tienda)
        serializer = CuponSerializer(cupon, data=request.data, partial=True, context={'tienda': tienda})
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                Tienda.objects.select_for_update().get(pk=tienda.id)
                serializer.save()
                notificar_cupon(cupon)
        except IntegrityError:
            raise ValidationError({'codigo': 'Ya existe ese código en esta tienda.'})
        registrar_auditoria(request, ACCION_ACTUALIZAR, tabla='cupon', registro_id=cupon.id,
                            datos_nuevos={'activo': cupon.activo, 'codigo': cupon.codigo})
        return Response(serializer.data)


class CuponesClienteView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsCliente]

    def get(self, request):
        hoy = timezone.localdate()
        qs = Cupon.objects.filter(activo=True, tienda__activa=True,
            fecha_inicio__lte=hoy, fecha_expiracion__gte=hoy).select_related(
            'tienda', 'segmento_objetivo', 'campana').annotate(n_usos=Count('usos')).filter(n_usos__lt=F('usos_maximos'))
        if request.query_params.get('tienda_id'):
            try:
                qs = qs.filter(tienda_id=int(request.query_params['tienda_id']))
            except ValueError:
                raise ValidationError({'tienda_id': 'La tienda no es válida.'})
        elegibles = [c for c in qs.order_by('-id')[:200] if es_destinatario(c, request.user)
                     and c.usos.filter(pedido__cliente=request.user).count() < c.limite_por_cliente]
        return Response(CuponSerializer(elegibles, many=True).data)


class ValidarCuponView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsCliente]

    def post(self, request):
        try:
            tienda_id = int(request.data.get('tienda_id', 0))
        except (ValueError, TypeError):
            raise ValidationError({'tienda_id': 'La tienda no es válida.'})
        carritos = Carrito.objects.filter(cliente=request.user, tienda_id=tienda_id).prefetch_related('items__variante')
        cotizaciones = cotizar_carritos(carritos, request.user, {str(tienda_id): request.data.get('codigo')})
        if not cotizaciones:
            raise ValidationError({'codigo': 'Agrega productos de esta tienda al carrito antes de aplicar el cupón.'})
        return Response(json_cotizacion(next(iter(cotizaciones.values()))))
