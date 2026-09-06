from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.tiendas.models import Tienda
from apps.usuarios.audit import ACCION_CREAR, registrar_auditoria
from apps.usuarios.permissions import IsEmpresa

from .models import Categoria, Producto
from .serializers import (
    CategoriaSerializer,
    ProductoCreateSerializer,
    ProductoSerializer,
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


class ProductoDetailView(OwnedStoreMixin, generics.RetrieveAPIView):
    serializer_class = ProductoSerializer
    lookup_url_kwarg = 'producto_id'

    def get_queryset(self):
        return Producto.objects.filter(
            tienda=self.get_tienda(),
        ).prefetch_related('variantes')
