"""
Vistas del módulo de Tiendas.
Sprint 0: Crear y listar tiendas del usuario autenticado.
"""

from rest_framework import generics, permissions

from apps.usuarios.audit import AuditoriaCreateMixin

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


class TiendaListCreateView(AuditoriaCreateMixin, generics.ListCreateAPIView):
    """
    GET  /api/tiendas/ — Listar tiendas del usuario autenticado (solo rol empresa).
    POST /api/tiendas/ — Crear nueva tienda (asociada al usuario como propietario).
    """
    serializer_class = TiendaSerializer
    permission_classes = [permissions.IsAuthenticated, IsEmpresaUser]
    audit_tabla = 'tienda'

    def get_queryset(self):
        return Tienda.objects.filter(propietario=self.request.user)

    def get_auditoria_extra_save_kwargs(self):
        return {'propietario': self.request.user}
