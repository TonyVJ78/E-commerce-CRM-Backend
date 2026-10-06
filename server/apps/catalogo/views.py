from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404

from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.tiendas.models import Tienda
from apps.usuarios.audit import ACCION_ACTUALIZAR, ACCION_CREAR, registrar_auditoria
from apps.usuarios.permissions import IsClienteUser, IsEmpresa

from .models import Categoria, Producto, Variante, VarianteStockMovimiento
from .serializers import (
    CategoriaSerializer,
    ProductoCatalogoSerializer,
    ProductoCreateSerializer,
    ProductoSerializer,
    StockAdjustmentInputSerializer,
    StockMovementSerializer,
    TiendaCatalogoSerializer,
)
from .services import (
    CloudinaryConfigurationError,
    CloudinaryUploadError,
    adjust_variant_stock,
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


class VarianteStockMovementView(OwnedStoreMixin, generics.ListCreateAPIView):
    """Ajuste manual y lectura del historial de una variante de tienda."""
    serializer_class = StockMovementSerializer
    http_method_names = ['get', 'post', 'head', 'options']

    def get_variante(self):
        return get_object_or_404(
            Variante.objects.select_related('producto'),
            pk=self.kwargs['variante_id'],
            producto__tienda=self.get_tienda(),
        )

    def get_queryset(self):
        return VarianteStockMovimiento.objects.filter(
            variante=self.get_variante(),
        ).select_related('actor', 'variante').order_by('-created_at', '-id')

    def create(self, request, *args, **kwargs):
        variante = self.get_variante()
        serializer = StockAdjustmentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            movimiento = adjust_variant_stock(
                variante_id=variante.pk,
                actor=request.user,
                **serializer.validated_data,
            )
        except ValidationError as exc:
            return Response({'detail': exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        # Registro en la bitácora central de auditoría del sistema (CU07 / HU-55)
        registrar_auditoria(
            request,
            ACCION_ACTUALIZAR,
            tabla='variante',
            registro_id=variante.pk,
            datos_previos={
                'stock': movimiento.previous_stock,
                'variante_sku': variante.sku,
                'producto_id': variante.producto_id,
            },
            datos_nuevos={
                'stock': movimiento.resulting_stock,
                'delta': movimiento.delta,
                'reason': movimiento.reason,
            },
        )

        return Response(
            StockMovementSerializer(movimiento).data,
            status=status.HTTP_201_CREATED,
        )


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


def _productos_publicos():
    """Productos a la venta (activos, de tiendas activas) con variantes activas."""
    variantes_activas = Variante.objects.filter(activa=True)
    return Producto.objects.filter(
        activo=True,
        tienda__activa=True,
    ).select_related('tienda', 'categoria').prefetch_related(
        Prefetch('variantes', queryset=variantes_activas)
    )


class ProductoCatalogoGeneralListView(generics.ListAPIView):
    """GET /api/catalogo/productos/ — Catálogo general de todas las tiendas con filtros avanzados."""

    serializer_class = ProductoCatalogoSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = _productos_publicos()

        tienda_id = self.request.query_params.get('tienda')
        if tienda_id:
            queryset = queryset.filter(tienda_id=tienda_id)

        categoria_id = self.request.query_params.get('categoria')
        if categoria_id:
            queryset = queryset.filter(categoria_id=categoria_id)

        categoria_nombre = self.request.query_params.get('categoria_nombre')
        if categoria_nombre and categoria_nombre.strip():
            queryset = queryset.filter(categoria__nombre__iexact=categoria_nombre.strip())

        q = self.request.query_params.get('q')
        if q and q.strip():
            q_clean = q.strip()
            queryset = queryset.filter(
                models.Q(nombre__icontains=q_clean) |
                models.Q(descripcion__icontains=q_clean) |
                models.Q(categoria__nombre__icontains=q_clean) |
                models.Q(tienda__nombre__icontains=q_clean)
            )

        # Filtro de stock disponible (en_stock=true)
        en_stock = self.request.query_params.get('en_stock')
        if en_stock in ('true', '1', 'True'):
            queryset = queryset.filter(variantes__activa=True, variantes__stock__gt=0).distinct()

        # Filtro de rango de precios sobre variantes activas
        precio_min = self.request.query_params.get('precio_min')
        if precio_min is not None:
            try:
                p_min = float(precio_min)
                queryset = queryset.filter(variantes__activa=True, variantes__precio__gte=p_min).distinct()
            except (ValueError, TypeError):
                pass

        precio_max = self.request.query_params.get('precio_max')
        if precio_max is not None:
            try:
                p_max = float(precio_max)
                queryset = queryset.filter(variantes__activa=True, variantes__precio__lte=p_max).distinct()
            except (ValueError, TypeError):
                pass

        # Ordenamiento
        orden = self.request.query_params.get('orden', 'recientes')
        if orden == 'precio_asc':
            queryset = queryset.order_by('variantes__precio', '-id').distinct()
        elif orden == 'precio_desc':
            queryset = queryset.order_by('-variantes__precio', '-id').distinct()
        elif orden == 'nombre_asc':
            queryset = queryset.order_by('nombre', '-id')
        elif orden == 'nombre_desc':
            queryset = queryset.order_by('-nombre', '-id')
        else:
            queryset = queryset.order_by('-creado', '-id')

        return queryset


class ProductoCatalogoDetailView(generics.RetrieveAPIView):
    """GET /api/catalogo/productos/<id>/ — Ficha pública de un producto.

    La usa la pestaña de detalle del producto (p. ej. al abrir una
    recomendación del chatbot). Solo muestra productos a la venta.
    """

    serializer_class = ProductoCatalogoSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return _productos_publicos()



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


