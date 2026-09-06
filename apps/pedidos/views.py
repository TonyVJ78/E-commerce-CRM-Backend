"""Endpoints del carrito requeridos por CU-11."""

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.usuarios.permissions import IsClienteUser

from .serializers import AgregarItemCarritoSerializer, ItemCarritoCreadoSerializer


class AgregarItemCarritoView(APIView):
    """POST /api/pedidos/carrito/items/ — Agregar una variante al carrito."""

    permission_classes = [permissions.IsAuthenticated, IsClienteUser]

    def post(self, request):
        serializer = AgregarItemCarritoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save(cliente=request.user)
        response_serializer = ItemCarritoCreadoSerializer(item)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
