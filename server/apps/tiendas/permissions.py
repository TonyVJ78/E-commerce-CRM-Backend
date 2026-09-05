"""
Permisos personalizados para el módulo de Tiendas y Productos.
Garantiza el aislamiento multitenant y control de roles RBAC.
"""

from rest_framework import permissions


class IsEmpresaUser(permissions.BasePermission):
    """Permiso que permite acceso únicamente a usuarios con rol 'empresa'."""
    message = "Solo los usuarios con rol 'empresa' pueden acceder a este recurso."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and hasattr(request.user, 'rol')
            and request.user.rol
            and request.user.rol.nombre == 'empresa'
        )


class IsProductoOwner(permissions.BasePermission):
    """
    Permiso que valida que solo el usuario propietario de la tienda
    asociada pueda consultar, editar o eliminar el producto.
    """
    message = "No tienes permisos sobre los productos de esta tienda."

    def has_object_permission(self, request, view, obj):
        return bool(
            request.user
            and request.user.is_authenticated
            and obj.tienda.propietario == request.user
        )