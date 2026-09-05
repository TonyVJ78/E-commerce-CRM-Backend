"""
Vistas del módulo de Tiendas y Productos.
CU09: Editar y Eliminar Productos.
"""

from rest_framework import exceptions, generics, permissions, status
from rest_framework.response import Response

from .models import Tienda, Producto
from .permissions import IsEmpresaUser, IsProductoOwner
from .serializers import TiendaSerializer, ProductoSerializer


class TiendaListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/tiendas/ — Listar tiendas del usuario autenticado (solo rol empresa).
    POST /api/tiendas/ — Crear nueva tienda (asociada al usuario como propietario).
    """
    serializer_class = TiendaSerializer
    permission_classes = [permissions.IsAuthenticated, IsEmpresaUser]

    def get_queryset(self):
        return Tienda.objects.filter(propietario=self.request.user)

    def perform_create(self, serializer):
        serializer.save(propietario=self.request.user)


class ProductoListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/tiendas/productos/ — Listar productos de las tiendas del usuario autenticado.
    POST /api/tiendas/productos/ — Crear nuevo producto validando la pertenencia de la tienda.
    """
    serializer_class = ProductoSerializer
    permission_classes = [permissions.IsAuthenticated, IsEmpresaUser]

    def get_queryset(self):
        # Aislamiento multitenant: solo productos activos de tiendas del usuario autenticado
        return Producto.objects.filter(tienda__propietario=self.request.user, activo=True)

    def perform_create(self, serializer):
        tienda = serializer.validated_data.get('tienda')
        if tienda.propietario != self.request.user:
            raise exceptions.PermissionDenied("No tienes permisos para agregar productos a esta tienda.")
        serializer.save()


class ProductoDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/tiendas/productos/<id>/ — Ver detalle del producto para edición.
    PUT    /api/tiendas/productos/<id>/ — Actualización completa del producto.
    PATCH  /api/tiendas/productos/<id>/ — Edición parcial de campos (precio, stock, etc.).
    DELETE /api/tiendas/productos/<id>/ — Baja lógica (marca activo=False).
    """
    queryset = Producto.objects.all()
    serializer_class = ProductoSerializer
    permission_classes = [permissions.IsAuthenticated, IsEmpresaUser, IsProductoOwner]

    def perform_destroy(self, instance):
        # Baja lógica: desactiva el producto en vez de eliminar la tupla física
        instance.activo = False
        instance.save()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(
            {'message': f'Producto "{instance.nombre}" eliminado del catálogo exitosamente.'},
            status=status.HTTP_200_OK
        )