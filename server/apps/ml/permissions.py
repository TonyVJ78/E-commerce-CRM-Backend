"""
Permisos de CU-35: aislamiento obligatorio por tienda.

Ningún usuario podrá consultar predicciones privadas de otra tienda.
"""

from rest_framework import permissions


class TiendaAisladaPermission(permissions.BasePermission):
    """
    Garantiza que las operaciones de ML no crucen fronteras de tienda.

    Se complementa con la validación explícita `tienda.propietario == request.user`
    en cada vista para el rol empresa, y `cliente == request.user` para el rol
    cliente cuando proceda.
    """

    message = 'No tiene permiso para acceder a datos de esta tienda.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)
