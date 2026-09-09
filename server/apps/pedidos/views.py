from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.usuarios.permissions import IsClienteUser

from .models import Carrito, ItemCarrito
from .serializers import (
    AgregarItemCarritoSerializer,
    ItemCarritoCreadoSerializer,
    ItemCarritoDetalleSerializer,
    CarritoDetalleSerializer,
)


class AgregarItemCarritoView(APIView):
    """POST /api/pedidos/carrito/items/ — Agregar una variante al carrito."""

    permission_classes = [permissions.IsAuthenticated, IsClienteUser]

    def post(self, request):
        serializer = AgregarItemCarritoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save(cliente=request.user)
        response_serializer = ItemCarritoCreadoSerializer(item)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class CarritoDetalleView(APIView):
    """GET /api/pedidos/carrito/ — Obtener el carrito y sus items del cliente actual.
    DELETE /api/pedidos/carrito/ — Vaciar el carrito.
    """

    permission_classes = [permissions.IsAuthenticated, IsClienteUser]

    def get(self, request):
        carritos = Carrito.objects.filter(
            cliente=request.user
        ).prefetch_related('items__variante__producto', 'items__tienda')

        serializer = CarritoDetalleSerializer(carritos, many=True)
        total_global = sum(float(c['total']) for c in serializer.data)
        total_items = sum(c['cantidad_items'] for c in serializer.data)

        return Response({
            'carritos': serializer.data,
            'total_items': total_items,
            'total_global': f"{total_global:.2f}",
        }, status=status.HTTP_200_OK)

    def delete(self, request):
        ItemCarrito.objects.filter(carrito__cliente=request.user).delete()
        return Response({'mensaje': 'Carrito vaciado exitosamente.'}, status=status.HTTP_200_OK)


class ItemCarritoDetailView(APIView):
    """PATCH /api/pedidos/carrito/items/<int:item_id>/ — Cambiar cantidad.
    DELETE /api/pedidos/carrito/items/<int:item_id>/ — Eliminar ítem del carrito.
    """

    permission_classes = [permissions.IsAuthenticated, IsClienteUser]

    def patch(self, request, item_id):
        item = get_object_or_404(ItemCarrito, pk=item_id, carrito__cliente=request.user)
        cantidad = request.data.get('cantidad')

        if cantidad is None or int(cantidad) <= 0:
            item.delete()
            return Response({'mensaje': 'Item eliminado del carrito.'}, status=status.HTTP_200_OK)

        item.cantidad = int(cantidad)
        item.save()
        serializer = ItemCarritoDetalleSerializer(item)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, item_id):
        item = get_object_or_404(ItemCarrito, pk=item_id, carrito__cliente=request.user)
        item.delete()
        return Response({'mensaje': 'Item eliminado del carrito.'}, status=status.HTTP_200_OK)

