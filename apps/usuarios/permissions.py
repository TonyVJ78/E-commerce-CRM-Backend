"""Permisos reutilizables basados en los roles de Kantu Market."""

from rest_framework import permissions


class IsClienteUser(permissions.BasePermission):
    """Permite el acceso únicamente a usuarios autenticados con rol Cliente."""

    message = "Solo los usuarios con rol 'cliente' pueden acceder a esta funcionalidad."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.rol
            and request.user.rol.nombre == 'cliente'
        )
