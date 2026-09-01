"""
Permisos reutilizables del módulo de Usuarios.
"""

from rest_framework import permissions


class IsAdministrador(permissions.BasePermission):
    """Permite el acceso únicamente a usuarios con rol 'administrador'."""
    message = "Solo los usuarios con rol 'administrador' pueden acceder a este recurso."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.rol
            and request.user.rol.nombre == 'administrador'
        )
