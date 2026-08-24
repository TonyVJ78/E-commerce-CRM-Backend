"""
Vistas del módulo de Tiendas.
Sprint 0: Crear y listar tiendas del usuario autenticado.
"""

from rest_framework import exceptions, generics, permissions

from .models import Tienda
from .serializers import TiendaSerializer


class IsEmpresaUser(permissions.BasePermission):
    """Permiso que permite acceso únicamente a usuarios con rol 'empresa'."""
    message = "Solo los usuarios con rol 'empresa' pueden crear o administrar tiendas."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.rol
            and request.user.rol.nombre == 'empresa'
        )


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
