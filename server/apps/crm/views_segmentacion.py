from datetime import timedelta
from decimal import Decimal
import logging
from smtplib import SMTPException
from uuid import uuid4

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.crm.models import ReglaSegmentacion, Segmento, SegmentoCliente
from apps.crm.serializers_segmentacion import (
    CampanaSegmentoPayloadSerializer,
    ClienteSegmentadoSerializer,
    ReglaSegmentacionSerializer,
)
from apps.crm.services.segmentacion_service import (
    resumen_segmentacion_tienda,
    recalcular_segmentos_tienda,
)
from apps.marketing.models import Campana, Cupon, NotificacionEnviada
from apps.tiendas.models import Tienda
from apps.usuarios.audit import ACCION_CREAR, ACCION_ACTUALIZAR, registrar_auditoria
from apps.usuarios.permissions import IsEmpresa

logger = logging.getLogger(__name__)


class SegmentacionTiendaMixin:
    permission_classes = [permissions.IsAuthenticated, IsEmpresa]

    def get_tienda(self, tienda_id):
        return get_object_or_404(Tienda, pk=tienda_id, propietario=self.request.user)


class SegmentacionClientesView(SegmentacionTiendaMixin, APIView):
    """Lista clientes segmentados y resumen de métricas de la tienda."""

    def get(self, request, tienda_id):
        tienda = self.get_tienda(tienda_id)
        queryset = SegmentoCliente.objects.filter(tienda=tienda).select_related('cliente')

        segmento = (request.query_params.get('segmento') or '').strip().upper()
        if segmento:
            if segmento not in dict(SegmentoCliente.SEGMENTO_CHOICES):
                return Response(
                    {'segmento': 'El segmento solicitado no es válido.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(segmento=segmento)

        busqueda = (request.query_params.get('q') or '').strip()
        if busqueda:
            queryset = queryset.filter(
                Q(cliente__first_name__icontains=busqueda)
                | Q(cliente__last_name__icontains=busqueda)
                | Q(cliente__email__icontains=busqueda)
            )

        return Response({
            'clientes': ClienteSegmentadoSerializer(queryset, many=True).data,
            'resumen': resumen_segmentacion_tienda(tienda),
        })


class RecalcularSegmentacionView(SegmentacionTiendaMixin, APIView):
    def post(self, request, tienda_id):
        tienda = self.get_tienda(tienda_id)
        resumen = recalcular_segmentos_tienda(tienda)
        return Response(resumen, status=status.HTTP_200_OK)


class ReglasSegmentacionView(SegmentacionTiendaMixin, APIView):
    def get(self, request, tienda_id):
        tienda = self.get_tienda(tienda_id)
        regla, _ = ReglaSegmentacion.objects.get_or_create(tienda=tienda)
        return Response(ReglaSegmentacionSerializer(regla).data)

    def patch(self, request, tienda_id):
        tienda = self.get_tienda(tienda_id)
        regla = ReglaSegmentacion.objects.filter(tienda=tienda).first()
        es_nueva = regla is None
        if regla is None:
            regla = ReglaSegmentacion(tienda=tienda)
        serializer = ReglaSegmentacionSerializer(regla, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        anterior = {
            'dias_inactividad': regla.dias_inactividad,
            'min_compras_frecuente': regla.min_compras_frecuente,
            'umbral_alto_valor': str(regla.umbral_alto_valor),
        }
        actualizada = serializer.save(tienda=tienda)
        registrar_auditoria(
            request,
            ACCION_CREAR if es_nueva else ACCION_ACTUALIZAR,
            tabla='regla_segmentacion',
            registro_id=actualizada.pk,
            datos_anteriores=None if es_nueva else anterior,
            datos_nuevos=serializer.data,
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class CampanaSegmentoView(SegmentacionTiendaMixin, APIView):
    """Envía una campaña/cupón al segmento seleccionado de una tienda."""

    def post(self, request, tienda_id):
        tienda = self.get_tienda(tienda_id)
        serializer = CampanaSegmentoPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        clientes = list(
            SegmentoCliente.objects.filter(
                tienda=tienda,
                segmento=datos['segmento'],
            )
            .select_related('cliente')
            .order_by('cliente_id')
        )
        if not clientes:
            return Response(
                {'detail': 'No hay clientes en el segmento seleccionado.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        hoy = timezone.localdate()
        fecha_expiracion = datos.get('fecha_expiracion') or (hoy + timedelta(days=30))
        codigo_cupon = datos['codigo_cupon']
        if datos['descuento_porcentaje'] > Decimal('0'):
            if codigo_cupon and Cupon.objects.filter(
                tienda=tienda,
                codigo__iexact=codigo_cupon,
            ).exists():
                return Response(
                    {'codigo_cupon': 'Ya existe un cupón con ese código en esta tienda.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        with transaction.atomic():
            segmento, _ = Segmento.objects.get_or_create(
                tienda=tienda,
                nombre=datos['segmento'],
                defaults={'criterio': f'Segmentación automática RFM: {datos["segmento"]}'},
            )
            campana = Campana.objects.create(
                tienda=tienda,
                segmento_objetivo=segmento,
                tipo='segmento',
                nombre=datos['nombre'],
                mensaje=datos['mensaje'],
                fecha_inicio=hoy,
                fecha_fin=fecha_expiracion,
            )
            if datos['descuento_porcentaje'] > Decimal('0'):
                if not codigo_cupon:
                    codigo_cupon = f'KM{campana.pk}{uuid4().hex[:8]}'.upper()[:30]
                    while Cupon.objects.filter(
                        tienda=tienda,
                        codigo__iexact=codigo_cupon,
                    ).exists():
                        codigo_cupon = f'KM{campana.pk}{uuid4().hex[:8]}'.upper()[:30]
                Cupon.objects.create(
                    tienda=tienda,
                    campana=campana,
                    codigo=codigo_cupon,
                    tipo_descuento='porcentaje',
                    valor_descuento=datos['descuento_porcentaje'],
                    fecha_expiracion=fecha_expiracion,
                    usos_maximos=len(clientes),
                )

        cuerpo = datos['mensaje'] or f'Usa el cupón {codigo_cupon} en tu próxima compra.'
        if codigo_cupon and datos['mensaje']:
            cuerpo = f'{cuerpo}\n\nCupón: {codigo_cupon}'
        if datos['descuento_porcentaje'] > Decimal('0'):
            cuerpo = (
                f'{cuerpo}\nDescuento: {datos["descuento_porcentaje"]}% '
                f'hasta el {fecha_expiracion.isoformat()}.'
            )

        enviados = 0
        fallidos = 0
        for fila in clientes:
            cliente = fila.cliente
            try:
                exito = send_mail(
                    subject=campana.nombre,
                    message=cuerpo,
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                    recipient_list=[cliente.email],
                    fail_silently=False,
                )
            except (SMTPException, OSError):
                logger.exception('No se pudo enviar la campaña %s a un destinatario.', campana.pk)
                exito = 0

            NotificacionEnviada.objects.create(
                tienda=tienda,
                campana=campana,
                cliente=cliente,
                canal='email',
                estado_entrega='enviado' if exito else 'fallido',
            )
            if exito:
                enviados += 1
            else:
                fallidos += 1

        registrar_auditoria(
            request,
            ACCION_CREAR,
            tabla='campana',
            registro_id=campana.pk,
            datos_nuevos={
                'tienda_id': tienda.pk,
                'segmento': datos['segmento'],
                'destinatarios': len(clientes),
                'enviados': enviados,
                'fallidos': fallidos,
                'cupon': codigo_cupon or None,
            },
        )
        return Response(
            {
                'mensaje': 'Campaña procesada para el segmento seleccionado.',
                'campana_id': campana.pk,
                'segmento': datos['segmento'],
                'destinatarios': len(clientes),
                'enviados': enviados,
                'fallidos': fallidos,
                'codigo_cupon': codigo_cupon or None,
            },
            status=status.HTTP_200_OK,
        )
