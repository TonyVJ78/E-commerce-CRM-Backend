"""Endpoints mínimos de catálogo requeridos por CU-11."""

from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions

from apps.tiendas.models import Tienda
from apps.usuarios.permissions import IsClienteUser

from .models import Producto, VarianteProducto
from .serializers import ProductoCatalogoSerializer, TiendaCatalogoSerializer


class TiendaCatalogoListView(generics.ListAPIView):
    """GET /api/catalogo/tiendas/ — Listar tiendas para el catálogo del Cliente."""

    serializer_class = TiendaCatalogoSerializer
    permission_classes = [permissions.IsAuthenticated, IsClienteUser]
    queryset = Tienda.objects.all()


class ProductoTiendaListView(generics.ListAPIView):
    """GET /api/catalogo/tiendas/<tienda_id>/productos/ — Catálogo de una tienda."""

    serializer_class = ProductoCatalogoSerializer
    permission_classes = [permissions.IsAuthenticated, IsClienteUser]

    def get_queryset(self):
        tienda_id = self.kwargs['tienda_id']
        get_object_or_404(Tienda, pk=tienda_id)

        variantes_tenant = VarianteProducto.objects.filter(tienda_id=tienda_id)
        return Producto.objects.filter(tienda_id=tienda_id).prefetch_related(
            Prefetch('variantes', queryset=variantes_tenant)
        )
