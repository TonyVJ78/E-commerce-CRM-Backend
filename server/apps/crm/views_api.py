from django.db.models import Min, Max, Sum, Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.pedidos.models import Pedido
from apps.tiendas.models import Tienda
from apps.usuarios.models import Usuario
from apps.usuarios.permissions import IsEmpresaUser
from .models import FichaCliente, InteraccionCliente, Segmento


class CrmClientesListView(APIView):
    """
    GET /api/tiendas/<tienda_id>/crm/clientes/
    Retorna la cartera de clientes de la tienda con metricas LTV, total pedidos y segmento (CU-15).
    """
    permission_classes = [permissions.IsAuthenticated, IsEmpresaUser]

    def get(self, request, tienda_id):
        tienda = get_object_or_404(Tienda, pk=tienda_id, propietario=request.user)

        # Clientes con pedidos o ficha registrada
        pedidos_qs = Pedido.objects.filter(tienda=tienda).exclude(estado_actual='cancelado')
        cliente_ids_pedidos = pedidos_qs.values_list('cliente_id', flat=True).distinct()
        cliente_ids_fichas = FichaCliente.objects.filter(tienda=tienda).values_list('cliente_id', flat=True).distinct()
        todos_cliente_ids = set(cliente_ids_pedidos).union(set(cliente_ids_fichas))

        fichas_map = {
            f.cliente_id: f
            for f in FichaCliente.objects.filter(tienda=tienda, cliente_id__in=todos_cliente_ids).select_related('segmento')
        }

        usuarios = Usuario.objects.filter(id__in=todos_cliente_ids)
        metricas = (
            pedidos_qs.values('cliente_id')
            .annotate(
                primera_compra=Min('fecha'),
                ultima_compra=Max('fecha'),
                ltv=Sum('total'),
                total_pedidos=Count('id'),
            )
        )
        metricas_map = {m['cliente_id']: m for m in metricas}

        resultados = []
        for u in usuarios:
            m = metricas_map.get(u.id, {})
            ficha = fichas_map.get(u.id)

            ltv_val = float(m.get('ltv') or 0.0)
            total_peds = int(m.get('total_pedidos') or 0)

            # Segmentacion
            if ficha and ficha.segmento:
                segmento_str = ficha.segmento.nombre
            elif ltv_val >= 1000 or total_peds >= 5:
                segmento_str = 'VIP'
            elif total_peds >= 2:
                segmento_str = 'Frecuente'
            elif total_peds == 1:
                segmento_str = 'Nuevo'
            else:
                segmento_str = 'Inactivo'

            nombre = f'{u.first_name} {u.last_name}'.strip() or u.email

            resultados.append({
                'id': u.id,
                'tienda_id': tienda.id,
                'nombre': nombre,
                'correo': u.email,
                'telefono': getattr(u, 'telefono', None) or '',
                'fecha_primera_compra': m.get('primera_compra').isoformat() if m.get('primera_compra') else None,
                'fecha_ultima_compra': m.get('ultima_compra').isoformat() if m.get('ultima_compra') else None,
                'ltv': ltv_val,
                'total_pedidos': total_peds,
                'segmento': segmento_str,
            })

        resultados.sort(key=lambda x: x['ltv'], reverse=True)
        return Response(resultados)


class CrmClienteDetalleView(APIView):
    """
    GET /api/tiendas/<tienda_id>/crm/clientes/<cliente_id>/
    Detalle comercial del cliente, historial de compras y fichas.
    """
    permission_classes = [permissions.IsAuthenticated, IsEmpresaUser]

    def get(self, request, tienda_id, cliente_id):
        tienda = get_object_or_404(Tienda, pk=tienda_id, propietario=request.user)
        cliente = get_object_or_404(Usuario, pk=cliente_id)

        ficha, _ = FichaCliente.objects.get_or_create(tienda=tienda, cliente=cliente)

        pedidos = (
            Pedido.objects.filter(tienda=tienda, cliente=cliente)
            .order_by('-fecha')
            .values('id', 'fecha', 'estado_actual', 'total')[:10]
        )

        interacciones = (
            InteraccionCliente.objects.filter(tienda=tienda, ficha_cliente=ficha)
            .order_by('-fecha')
            .values('id', 'tipo', 'mensaje', 'fecha', 'estado')
        )

        nombre = f'{cliente.first_name} {cliente.last_name}'.strip() or cliente.email

        return Response({
            'id': cliente.id,
            'tienda_id': tienda.id,
            'nombre': nombre,
            'correo': cliente.email,
            'telefono': getattr(cliente, 'telefono', None) or '',
            'segmento': ficha.segmento.nombre if ficha.segmento else 'General',
            'historial_compras': list(pedidos),
            'interacciones': list(interacciones),
        })


class CrmInteraccionesView(APIView):
    """
    GET/POST /api/tiendas/<tienda_id>/crm/clientes/<cliente_id>/interacciones/
    Listado y registro de interacciones comerciales (CU-15).
    """
    permission_classes = [permissions.IsAuthenticated, IsEmpresaUser]

    def get(self, request, tienda_id, cliente_id):
        tienda = get_object_or_404(Tienda, pk=tienda_id, propietario=request.user)
        cliente = get_object_or_404(Usuario, pk=cliente_id)
        ficha, _ = FichaCliente.objects.get_or_create(tienda=tienda, cliente=cliente)

        interacciones = InteraccionCliente.objects.filter(
            tienda=tienda, ficha_cliente=ficha
        ).order_by('-fecha')

        data = [
            {
                'id': i.id,
                'cliente_id': cliente.id,
                'tienda_id': tienda.id,
                'tipo': i.tipo,
                'mensaje': i.mensaje,
                'fecha': i.fecha.isoformat() if i.fecha else timezone.now().isoformat(),
                'estado': i.estado,
            }
            for i in interacciones
        ]
        return Response(data)

    def post(self, request, tienda_id, cliente_id):
        tienda = get_object_or_404(Tienda, pk=tienda_id, propietario=request.user)
        cliente = get_object_or_404(Usuario, pk=cliente_id)
        ficha, _ = FichaCliente.objects.get_or_create(tienda=tienda, cliente=cliente)

        tipo = request.data.get('tipo', 'Consulta')
        mensaje = request.data.get('mensaje', '').strip()
        estado = request.data.get('estado', 'Resuelto')

        if not mensaje:
            return Response({'mensaje': ['El mensaje es obligatorio.']}, status=status.HTTP_400_BAD_REQUEST)

        interaccion = InteraccionCliente.objects.create(
            tienda=tienda,
            ficha_cliente=ficha,
            tipo=tipo,
            mensaje=mensaje,
            estado=estado,
        )

        return Response({
            'id': interaccion.id,
            'cliente_id': cliente.id,
            'tienda_id': tienda.id,
            'tipo': interaccion.tipo,
            'mensaje': interaccion.mensaje,
            'fecha': interaccion.fecha.isoformat(),
            'estado': interaccion.estado,
        }, status=status.HTTP_201_CREATED)
