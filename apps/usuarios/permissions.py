"""
Permisos reutilizables basados en los roles de Kantu Market.

Los roles semilla (`administrador`, `empresa`, `cliente`) se crean en la migración
`usuarios/0002_roles_semilla.py`. Las clases `Is*` de este módulo comparan
`request.user.rol.nombre` contra ese string.

CU07 añade el control de acceso **por permiso** (`TienePermiso('codigo')`), que
consulta la tabla `rol_permiso` en vez de comparar el nombre del rol. El catálogo
de permisos y su mapeo a los roles semilla se siembran en
`usuarios/0005_permisos_semilla.py`.

Este es el único lugar donde deben vivir los permisos: si necesitás uno nuevo,
agregalo acá en vez de declararlo dentro de una vista.
"""

from rest_framework import permissions

from .models import RolPermiso


class _RolRequeridoPermission(permissions.BasePermission):
    """Base: concede acceso solo a usuarios autenticados con un rol concreto.

    Las subclases definen `rol_requerido` y, opcionalmente, `message`.
    """

    rol_requerido = None

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.rol
            and request.user.rol.nombre == self.rol_requerido
        )


class IsAdministrador(_RolRequeridoPermission):
    """Permite el acceso únicamente a usuarios con rol 'administrador'."""
    rol_requerido = 'administrador'
    message = "Solo los usuarios con rol 'administrador' pueden acceder a este recurso."


class IsEmpresaUser(_RolRequeridoPermission):
    """Permite el acceso únicamente a usuarios con rol 'empresa'."""
    rol_requerido = 'empresa'
    message = "Solo los usuarios con rol 'empresa' pueden acceder a este recurso."


class IsClienteUser(_RolRequeridoPermission):
    """Permite el acceso únicamente a usuarios con rol 'cliente'."""
    rol_requerido = 'cliente'
    message = "Solo los usuarios con rol 'cliente' pueden acceder a esta funcionalidad."


def usuario_tiene_permiso(usuario, codigo):
    """`True` si el usuario tiene concedido el permiso `codigo` a través de su rol.

    El superusuario de Django siempre lo tiene. Un usuario anónimo o sin rol,
    nunca.
    """
    if usuario is None or not getattr(usuario, 'is_authenticated', False):
        return False
    if usuario.is_superuser:
        return True
    if usuario.rol_id is None:
        return False
    return RolPermiso.objects.filter(
        rol_id=usuario.rol_id, permiso__codigo=codigo
    ).exists()


def TienePermiso(codigo):
    """Fábrica de permisos DRF: exige que el rol del usuario tenga `codigo`.

    Uso: ``permission_classes = [permissions.IsAuthenticated, TienePermiso('ver_bitacora')]``

    Es el reemplazo "avanzado" de las clases `Is*`: en vez de atar la vista al
    nombre de un rol, la ata a una capacidad concreta que el administrador
    puede reasignar entre roles desde la pantalla de Accesos.
    """

    class _TienePermiso(permissions.BasePermission):
        message = f"Se requiere el permiso '{codigo}' para acceder a este recurso."

        def has_permission(self, request, view):
            return usuario_tiene_permiso(request.user, codigo)

    _TienePermiso.__name__ = f'TienePermiso_{codigo}'
    return _TienePermiso
