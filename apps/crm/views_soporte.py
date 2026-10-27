"""
Controladores REST API para CU-26: Registrar consulta / reclamo (Atención al cliente y gestión de tickets postventa).
"""

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.crm.models import TicketSoporte, MensajeTicket
from apps.crm.serializers import (
    TicketSoporteSerializer,
    CrearTicketSerializer,
    CrearMensajeTicketSerializer,
    MensajeTicketSerializer,
)
from apps.tiendas.models import Tienda
from apps.pedidos.models import Pedido
from apps.usuarios.audit import ACCION_CREAR, ACCION_ACTUALIZAR, registrar_auditoria


def _get_tienda_vendedor(request, tienda_id):
    """Verifica permisos de tienda para el vendedor o superusuario."""
    if getattr(request.user, 'is_superuser', False):
        return get_object_or_404(Tienda, pk=tienda_id)
    return get_object_or_404(Tienda, pk=tienda_id, propietario=request.user)


class TicketClienteCrearView(APIView):
    """
    POST /api/soporte/tickets/
    Creación de ticket de soporte o reclamo por parte del cliente.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CrearTicketSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        pedido_obj = data.get('pedido_obj')
        tienda_id = data.get('tienda_id')

        if pedido_obj:
            tienda = pedido_obj.tienda
            pedido = pedido_obj
        else:
            tienda = get_object_or_404(Tienda, pk=tienda_id)
            pedido = None

        ticket = TicketSoporte.objects.create(
            cliente=request.user,
            tienda=tienda,
            pedido=pedido,
            tipo=data.get('tipo', 'consulta'),
            prioridad=data.get('prioridad', 'media'),
            asunto=data['asunto'],
            descripcion=data['descripcion'],
        )

        # Crear el primer mensaje en el hilo
        MensajeTicket.objects.create(
            ticket=ticket,
            autor=request.user,
            contenido=data['descripcion'],
            archivo_adjunto=data.get('archivo_adjunto'),
        )

        # Registrar en auditoria (CU-23)
        registrar_auditoria(
            request,
            ACCION_CREAR,
            tabla='ticket_soporte',
            registro_id=ticket.id,
            datos_nuevos={
                'codigo_ticket': ticket.codigo_ticket,
                'tipo': ticket.tipo,
                'asunto': ticket.asunto,
                'tienda_id': tienda.id,
                'pedido_id': pedido.id if pedido else None,
            },
        )

        salida = TicketSoporteSerializer(ticket)
        return Response(salida.data, status=status.HTTP_201_CREATED)


class MisTicketsClienteListView(APIView):
    """
    GET /api/soporte/tickets/mis-tickets/
    Listado de tickets creados por el cliente autenticado.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        tickets = (
            TicketSoporte.objects.filter(cliente=request.user)
            .select_related('tienda', 'pedido', 'cliente')
            .prefetch_related('mensajes', 'mensajes__autor')
            .order_by('-fecha_creacion')
        )
        serializer = TicketSoporteSerializer(tickets, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DetalleTicketView(APIView):
    """
    GET /api/soporte/tickets/<id>/
    Detalle completo de un ticket y su historial de respuestas.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        ticket = get_object_or_404(
            TicketSoporte.objects.select_related('tienda', 'pedido', 'cliente').prefetch_related(
                'mensajes', 'mensajes__autor'
            ),
            pk=pk,
        )

        # Validación de pertenencia: Cliente o Vendedor dueño de la tienda o Superuser
        es_cliente = ticket.cliente_id == request.user.id
        es_vendedor = ticket.tienda.propietario_id == request.user.id
        es_admin = getattr(request.user, 'is_superuser', False)

        if not (es_cliente or es_vendedor or es_admin):
            return Response(
                {'detail': 'No tienes permisos para visualizar este ticket.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = TicketSoporteSerializer(ticket)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ResponderTicketView(APIView):
    """
    POST /api/soporte/tickets/<id>/responder/
    Agrega una respuesta al hilo del ticket.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        ticket = get_object_or_404(TicketSoporte.objects.select_related('tienda'), pk=pk)

        es_cliente = ticket.cliente_id == request.user.id
        es_vendedor = ticket.tienda.propietario_id == request.user.id
        es_admin = getattr(request.user, 'is_superuser', False)

        if not (es_cliente or es_vendedor or es_admin):
            return Response(
                {'detail': 'No tienes permisos para responder a este ticket.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CrearMensajeTicketSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        mensaje = MensajeTicket.objects.create(
            ticket=ticket,
            autor=request.user,
            contenido=serializer.validated_data['contenido'],
            archivo_adjunto=serializer.validated_data.get('archivo_adjunto'),
        )

        # Transición reactiva de estado según quién responda
        if es_vendedor or es_admin:
            if ticket.estado == 'abierto':
                ticket.estado = 'en_proceso'
                ticket.save(update_fields=['estado', 'fecha_actualizacion'])
        elif es_cliente:
            if ticket.estado in ('resuelto', 'cerrado'):
                ticket.estado = 'en_proceso'
                ticket.save(update_fields=['estado', 'fecha_actualizacion'])

        return Response(MensajeTicketSerializer(mensaje).data, status=status.HTTP_201_CREATED)


class TiendaTicketsListView(APIView):
    """
    GET /api/tiendas/<tienda_id>/tickets/
    Listado de tickets recibidos por la tienda del vendedor con filtros por estado y prioridad.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, tienda_id):
        tienda = _get_tienda_vendedor(request, tienda_id)

        queryset = (
            TicketSoporte.objects.filter(tienda=tienda)
            .select_related('cliente', 'pedido', 'tienda')
            .prefetch_related('mensajes', 'mensajes__autor')
            .order_by('-fecha_creacion')
        )

        # Filtros opcionales
        estado = request.query_params.get('estado')
        if estado:
            queryset = queryset.filter(estado=estado)

        prioridad = request.query_params.get('prioridad')
        if prioridad:
            queryset = queryset.filter(prioridad=prioridad)

        tipo = request.query_params.get('tipo')
        if tipo:
            queryset = queryset.filter(tipo=tipo)

        # Metricas KPI para la cabecera
        base_tienda = TicketSoporte.objects.filter(tienda=tienda)
        resumen_kpi = {
            'total_abiertos': base_tienda.filter(estado='abierto').count(),
            'total_en_proceso': base_tienda.filter(estado='en_proceso').count(),
            'total_resueltos': base_tienda.filter(estado__in=['resuelto', 'cerrado']).count(),
            'total_tickets': base_tienda.count(),
        }

        serializer = TicketSoporteSerializer(queryset, many=True)
        return Response({
            'kpis': resumen_kpi,
            'tickets': serializer.data,
        }, status=status.HTTP_200_OK)


class TiendaActualizarEstadoTicketView(APIView):
    """
    PATCH /api/tiendas/<tienda_id>/tickets/<id>/estado/
    Actualización rápida del estado del ticket por parte del vendedor.
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, tienda_id, pk):
        tienda = _get_tienda_vendedor(request, tienda_id)
        ticket = get_object_or_404(TicketSoporte, pk=pk, tienda=tienda)

        nuevo_estado = request.data.get('estado')
        estados_validos = dict(TicketSoporte.ESTADO_CHOICES).keys()

        if nuevo_estado not in estados_validos:
            return Response(
                {'detail': f'Estado invalido. Opciones validas: {list(estados_validos)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        estado_anterior = ticket.estado
        ticket.estado = nuevo_estado
        ticket.save()

        # Auditoria
        registrar_auditoria(
            request,
            ACCION_ACTUALIZAR,
            tabla='ticket_soporte',
            registro_id=ticket.id,
            datos_anteriores={'estado': estado_anterior},
            datos_nuevos={'estado': nuevo_estado},
        )

        serializer = TicketSoporteSerializer(ticket)
        return Response(serializer.data, status=status.HTTP_200_OK)
