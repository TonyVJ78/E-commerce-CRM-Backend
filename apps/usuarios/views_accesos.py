"""
Vistas del CU07 — Gestionar roles y permisos.

Actor: Administrador (módulo "Accesos Avanzados"). El acceso se controla con la
matriz módulo × acción (`permissions.PermisoModulo`): las vistas de roles/permisos
exigen `accesos.<accion>` y las de usuarios `usuarios.<accion>`, donde la acción
sale del método HTTP (GET→ver, POST→crear, PUT/PATCH→editar, DELETE→eliminar). El
catálogo se siembra en `0006_matriz_permisos.py`.

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
from .permissions import PermisoModulo
from .serializers import (
    ROLES_SEMILLA,
    PermisoSerializer,
    RolConPermisosSerializer,
    RolPermisosUpdateSerializer,
    UsuarioAdminSerializer,
)

Usuario = get_user_model()

ACCESOS = [permissions.IsAuthenticated, PermisoModulo('accesos')]
USUARIOS = [permissions.IsAuthenticated, PermisoModulo('usuarios')]


class RolEnUsoError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'No se puede eliminar el rol: hay usuarios que lo tienen asignado.'
    default_code = 'rol_en_uso'


class RolListCreateView(AuditoriaCreateMixin, generics.ListCreateAPIView):
    """GET /api/roles/ · POST /api/roles/ — Listar y crear roles."""
    serializer_class = RolConPermisosSerializer
    permission_classes = ACCESOS
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
    permission_classes = ACCESOS
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
    permission_classes = ACCESOS

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

        # Un admin no-superuser no puede dejar a su propio rol sin las llaves con
        # las que administra accesos (si no, se autobloquea de esta pantalla).
        if rol.pk == request.user.rol_id and not request.user.is_superuser:
            criticos = {'accesos.ver', 'accesos.editar'}
            tenia = set(
                Permiso.objects.filter(pk__in=actuales, codigo__in=criticos)
                .values_list('codigo', flat=True)
            )
            conserva = set(
                Permiso.objects.filter(pk__in=nuevos, codigo__in=criticos)
                .values_list('codigo', flat=True)
            )
            if tenia - conserva:
                raise ValidationError(
                    'No puedes quitarle a tu propio rol los permisos con los que '
                    'gestionas accesos (accesos.ver / accesos.editar).'
                )

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
    permission_classes = ACCESOS
    queryset = Permiso.objects.all().order_by('nombre')
    pagination_class = None


class UsuariosPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 200


class UsuarioAdminListView(generics.ListAPIView):
    """GET /api/usuarios/ — Listar usuarios para asignarles rol (filtros: rol, activo, buscar)."""
    serializer_class = UsuarioAdminSerializer
    permission_classes = USUARIOS
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
    permission_classes = USUARIOS
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
