"""Endpoints del motor determinístico de recomendaciones de CU-14."""

from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalogo.serializers import ProductoCatalogoSerializer
from apps.tiendas.models import Tienda
from apps.usuarios.permissions import IsClienteUser

from .serializers import (
    InteraccionProductoSerializer,
    InteraccionRegistradaSerializer,
    RecomendacionQuerySerializer,
)
from .services import obtener_recomendaciones_cliente


class RecomendacionesTiendaView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsClienteUser]

    def get(self, request, tienda_id):
        tienda = get_object_or_404(Tienda, pk=tienda_id, activa=True)
        query = RecomendacionQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        products = obtener_recomendaciones_cliente(
            cliente=request.user,
            tienda=tienda,
            limit=query.validated_data['limit'],
        )
        return Response(
            ProductoCatalogoSerializer(products, many=True).data,
            status=status.HTTP_200_OK,
        )


class InteraccionProductoView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsClienteUser]

    def post(self, request):
        serializer = InteraccionProductoSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        event = serializer.save()
        return Response(
            InteraccionRegistradaSerializer(event).data,
            status=status.HTTP_201_CREATED,
        )
