"""
Vistas del CU07 — Gestionar roles y permisos.

Actor: Administrador (módulo "Accesos Avanzados"). Todo el módulo exige el
permiso `gestionar_accesos` (ver `permissions.TienePermiso`), que la migración
`0005_permisos_semilla.py` concede al rol `administrador`.

Endpoints (montados en `config/urls.py` bajo `/api/`):
- GET/POST        /api/roles/
- GET/PATCH/DELETE /api/roles/<pk>/
- GET/PUT         /api/roles/<pk>/permisos/
- GET            /api/permisos/
- GET            /api/usuarios/
- GET/PATCH      /api/usuarios/<pk>/
"""

from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from rest_framework import generics, permissions, status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .audit import (
    ACCION_ACTUALIZAR,
    AuditoriaCreateMixin,
    AuditoriaDeleteMixin,
    AuditoriaUpdateMixin,
    registrar_auditoria,
)
from .models import Permiso, Rol, RolPermiso
from .permissions import TienePermiso
from .serializers import (
    ROLES_SEMILLA,
    PermisoSerializer,
    RolConPermisosSerializer,
    RolPermisosUpdateSerializer,
    UsuarioAdminSerializer,
)

Usuario = get_user_model()

GESTIONAR_ACCESOS = [permissions.IsAuthenticated, TienePermiso('gestionar_accesos')]


class RolEnUsoError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'No se puede eliminar el rol: hay usuarios que lo tienen asignado.'
    default_code = 'rol_en_uso'


class RolListCreateView(AuditoriaCreateMixin, generics.ListCreateAPIView):
    """GET /api/roles/ · POST /api/roles/ — Listar y crear roles."""
    serializer_class = RolConPermisosSerializer
    permission_classes = GESTIONAR_ACCESOS
    audit_tabla = 'rol'

    def get_queryset(self):
        return Rol.objects.prefetch_related('roles_permisos__permiso', 'usuarios').order_by('nombre')


class RolDetailView(AuditoriaUpdateMixin, AuditoriaDeleteMixin,
                    generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/roles/<pk>/ — Ver, renombrar o eliminar un rol.

    Los roles semilla (`administrador`, `empresa`, `cliente`) no se pueden
    renombrar (lo valida el serializer) ni eliminar.
    """
    serializer_class = RolConPermisosSerializer
    permission_classes = GESTIONAR_ACCESOS
    audit_tabla = 'rol'
    queryset = Rol.objects.prefetch_related('roles_permisos__permiso', 'usuarios')

    def perform_destroy(self, instance):
        if instance.nombre in ROLES_SEMILLA:
            raise ValidationError('Los roles del sistema no se pueden eliminar.')
        try:
            super().perform_destroy(instance)
        except ProtectedError:
            raise RolEnUsoError()


class RolPermisosView(APIView):
    """GET/PUT /api/roles/<pk>/permisos/ — Consultar y reemplazar los permisos de un rol."""
    permission_classes = GESTIONAR_ACCESOS

    def get_object(self, pk):
        try:
            return Rol.objects.get(pk=pk)
        except Rol.DoesNotExist:
            raise ValidationError('El rol no existe.')

    def get(self, request, pk):
        rol = self.get_object(pk)
        asignados = list(
            rol.roles_permisos.values_list('permiso_id', flat=True)
        )
        return Response({
            'asignados': asignados,
            'disponibles': PermisoSerializer(
                Permiso.objects.all().order_by('nombre'), many=True
            ).data,
        })

    def put(self, request, pk):
        rol = self.get_object(pk)
        serializer = RolPermisosUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        nuevos = {p.pk for p in serializer.validated_data['permisos']}
        actuales = set(rol.roles_permisos.values_list('permiso_id', flat=True))

        a_agregar = nuevos - actuales
        a_quitar = actuales - nuevos

        RolPermiso.objects.filter(rol=rol, permiso_id__in=a_quitar).delete()
        RolPermiso.objects.bulk_create(
            [RolPermiso(rol=rol, permiso_id=pid) for pid in a_agregar]
        )

        if a_agregar or a_quitar:
            registrar_auditoria(
                request,
                ACCION_ACTUALIZAR,
                tabla='rol_permiso',
                registro_id=rol.pk,
                datos_anteriores={'permisos': sorted(actuales)},
                datos_nuevos={'permisos': sorted(nuevos)},
            )

        return Response({'asignados': sorted(nuevos)})


class PermisoListView(generics.ListAPIView):
    """GET /api/permisos/ — Catálogo de permisos (solo lectura; lo define el sistema)."""
    serializer_class = PermisoSerializer
    permission_classes = GESTIONAR_ACCESOS
    queryset = Permiso.objects.all().order_by('nombre')
    pagination_class = None


class UsuariosPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 200


class UsuarioAdminListView(generics.ListAPIView):
    """GET /api/usuarios/ — Listar usuarios para asignarles rol (filtros: rol, activo, buscar)."""
    serializer_class = UsuarioAdminSerializer
    permission_classes = GESTIONAR_ACCESOS
    pagination_class = UsuariosPagination

    def get_queryset(self):
        qs = Usuario.objects.select_related('rol').order_by('email')
        params = self.request.query_params

        rol = params.get('rol')
        if rol:
            qs = qs.filter(rol__nombre__iexact=rol)

        activo = params.get('activo')
        if activo in ('true', 'false'):
            qs = qs.filter(activo=(activo == 'true'))

        buscar = params.get('buscar')
        if buscar:
            from django.db.models import Q
            qs = qs.filter(
                Q(email__icontains=buscar)
                | Q(first_name__icontains=buscar)
                | Q(last_name__icontains=buscar)
            )
        return qs


class UsuarioAdminDetailView(AuditoriaUpdateMixin, generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/usuarios/<pk>/ — Cambiar el rol y el estado (activo) de un usuario."""
    serializer_class = UsuarioAdminSerializer
    permission_classes = GESTIONAR_ACCESOS
    audit_tabla = 'usuario'
    queryset = Usuario.objects.select_related('rol')
    http_method_names = ['get', 'patch', 'head', 'options']

    def perform_update(self, serializer):
        instance = serializer.instance
        if instance.pk == self.request.user.pk:
            nuevo_rol = serializer.validated_data.get('rol', instance.rol)
            nuevo_activo = serializer.validated_data.get('activo', instance.activo)
            if nuevo_rol != instance.rol or not nuevo_activo:
                raise ValidationError(
                    'No puedes cambiar tu propio rol ni desactivar tu propia cuenta.'
                )
        # `is_active` sigue a `activo` para mantener coherencia con AbstractUser.
        if 'activo' in serializer.validated_data:
            serializer.validated_data['is_active'] = serializer.validated_data['activo']
        super().perform_update(serializer)
