from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404

from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.tiendas.models import Tienda
from apps.usuarios.audit import ACCION_CREAR, registrar_auditoria
from apps.usuarios.permissions import IsClienteUser, IsEmpresa

from .models import Categoria, Producto, Variante
from .serializers import (
    CategoriaSerializer,
    ProductoCatalogoSerializer,
    ProductoCreateSerializer,
    ProductoSerializer,
    TiendaCatalogoSerializer,
)
from .services import (
    CloudinaryConfigurationError,
    CloudinaryUploadError,
    create_product_with_images,
)


class OwnedStoreMixin:
    permission_classes = [permissions.IsAuthenticated, IsEmpresa]

    def get_tienda(self):
        return get_object_or_404(
            Tienda,
            pk=self.kwargs['tienda_id'],
            propietario=self.request.user,
        )


class CategoriaListView(OwnedStoreMixin, generics.ListAPIView):
    serializer_class = CategoriaSerializer

    def get_queryset(self):
        return Categoria.objects.filter(tienda=self.get_tienda()).order_by('nombre', 'id')


class ProductoListCreateView(OwnedStoreMixin, generics.ListCreateAPIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        return Producto.objects.filter(
            tienda=self.get_tienda(),
        ).prefetch_related('variantes').order_by('-creado', '-id')

    def get_serializer_class(self):
        return ProductoSerializer if self.request.method == 'GET' else ProductoCreateSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['tienda'] = self.get_tienda()
        return context

    def create(self, request, *args, **kwargs):
        tienda = self.get_tienda()
        serializer = ProductoCreateSerializer(
            data=request.data,
            context={**self.get_serializer_context(), 'tienda': tienda},
        )
        serializer.is_valid(raise_exception=True)

        try:
            producto = create_product_with_images(
                tienda=tienda,
                validated_data=serializer.validated_data,
            )
        except (CloudinaryConfigurationError, CloudinaryUploadError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except ValidationError as exc:
            return Response({'detail': exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        output = ProductoSerializer(producto, context=self.get_serializer_context())
        registrar_auditoria(
            request,
            ACCION_CREAR,
            tabla='producto',
            registro_id=producto.pk,
            datos_nuevos=output.data,
        )
        return Response(output.data, status=status.HTTP_201_CREATED)


class ProductoDetailView(OwnedStoreMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProductoSerializer
    lookup_url_kwarg = 'producto_id'

    def get_queryset(self):
        return Producto.objects.filter(
            tienda=self.get_tienda(),
        ).prefetch_related('variantes')

    def perform_destroy(self, instance):
        """Borrado lógico (soft-delete) para mantener integridad con pedidos históricos."""
        instance.activo = False
        instance.save(update_fields=['activo'])


# =========================================================================
# Vistas de Catálogo Público para Clientes y Visitantes (CU-11)
# =========================================================================

class TiendaCatalogoListView(generics.ListAPIView):
    """GET /api/catalogo/tiendas/ — Listar tiendas para el catálogo público."""

    serializer_class = TiendaCatalogoSerializer
    permission_classes = [permissions.AllowAny]
    queryset = Tienda.objects.filter(activa=True)


class ProductoTiendaListView(generics.ListAPIView):
    """GET /api/catalogo/tiendas/<tienda_id>/productos/ — Catálogo de una tienda."""

    serializer_class = ProductoCatalogoSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        tienda_id = self.kwargs['tienda_id']
        get_object_or_404(Tienda, pk=tienda_id)

        variantes_activas = Variante.objects.filter(activa=True)
        return Producto.objects.filter(tienda_id=tienda_id, activo=True).prefetch_related(
            Prefetch('variantes', queryset=variantes_activas)
        )


class ProductoCatalogoGeneralListView(generics.ListAPIView):
    """GET /api/catalogo/productos/ — Catálogo general de todas las tiendas con filtros."""

    serializer_class = ProductoCatalogoSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        variantes_activas = Variante.objects.filter(activa=True)
        queryset = Producto.objects.filter(
            activo=True,
            tienda__activa=True,
        ).select_related('tienda', 'categoria').prefetch_related(
            Prefetch('variantes', queryset=variantes_activas)
        )

        tienda_id = self.request.query_params.get('tienda')
        if tienda_id:
            queryset = queryset.filter(tienda_id=tienda_id)

        categoria_id = self.request.query_params.get('categoria')
        if categoria_id:
            queryset = queryset.filter(categoria_id=categoria_id)

        q = self.request.query_params.get('q')
        if q:
            queryset = queryset.filter(
                models.Q(nombre__icontains=q) |
                models.Q(descripcion__icontains=q) |
                models.Q(categoria__nombre__icontains=q) |
                models.Q(tienda__nombre__icontains=q)
            )

        return queryset.order_by('-id')


class CategoriaCatalogoListView(generics.ListAPIView):
    """GET /api/catalogo/categorias/ — Listar categorías activas para filtrado."""

    serializer_class = CategoriaSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        tienda_id = self.request.query_params.get('tienda')
        qs = Categoria.objects.all()
        if tienda_id:
            qs = qs.filter(tienda_id=tienda_id)
        return qs.order_by('nombre')


