"""
Vistas del CU07 — Bitácora.

Solo el rol 'administrador' puede consultar:
- GET /api/auditoria/bitacora/  → registros de inicio de sesión (bitacora_acceso)
- GET /api/auditoria/logs/      → cambios en la base de datos y cierres de sesión (log_auditoria)

Ambos endpoints están paginados y admiten filtros por querystring.
"""

import django_filters
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics, permissions
from rest_framework.pagination import PageNumberPagination

from .models import BitacoraAcceso, LogAuditoria
from .permissions import TienePermiso
from .serializers import BitacoraAccesoSerializer, LogAuditoriaSerializer


class AuditoriaPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 200


class BitacoraAccesoFilter(django_filters.FilterSet):
    usuario = django_filters.CharFilter(method='filtrar_usuario')
    ip = django_filters.CharFilter(field_name='ip', lookup_expr='icontains')
    exitoso = django_filters.BooleanFilter(field_name='exitoso')
    fecha_desde = django_filters.DateFilter(field_name='fecha', lookup_expr='date__gte')
    fecha_hasta = django_filters.DateFilter(field_name='fecha', lookup_expr='date__lte')

    class Meta:
        model = BitacoraAcceso
        fields = ['usuario', 'ip', 'exitoso', 'fecha_desde', 'fecha_hasta']

    def filtrar_usuario(self, queryset, name, value):
        """Busca por email del usuario registrado o por el email del intento."""
        return queryset.filter(
            Q(usuario__email__icontains=value) | Q(email_intento__icontains=value)
        )


class LogAuditoriaFilter(django_filters.FilterSet):
    usuario = django_filters.CharFilter(field_name='usuario__email', lookup_expr='icontains')
    tabla = django_filters.CharFilter(field_name='tabla_afectada', lookup_expr='iexact')
    accion = django_filters.CharFilter(field_name='accion', lookup_expr='iexact')
    fecha_desde = django_filters.DateFilter(field_name='fecha', lookup_expr='date__gte')
    fecha_hasta = django_filters.DateFilter(field_name='fecha', lookup_expr='date__lte')

    class Meta:
        model = LogAuditoria
        fields = ['usuario', 'tabla', 'accion', 'fecha_desde', 'fecha_hasta']


class BitacoraAccesoListView(generics.ListAPIView):
    """GET /api/auditoria/bitacora/ — Bitácora de inicios de sesión."""
    serializer_class = BitacoraAccesoSerializer
    permission_classes = [permissions.IsAuthenticated, TienePermiso('ver_bitacora')]
    pagination_class = AuditoriaPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = BitacoraAccesoFilter
    ordering_fields = ['fecha']
    ordering = ['-fecha']
    queryset = BitacoraAcceso.objects.select_related('usuario').all()


class LogAuditoriaListView(generics.ListAPIView):
    """GET /api/auditoria/logs/ — Log de cambios en la base de datos y cierres de sesión."""
    serializer_class = LogAuditoriaSerializer
    permission_classes = [permissions.IsAuthenticated, TienePermiso('ver_bitacora')]
    pagination_class = AuditoriaPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = LogAuditoriaFilter
    ordering_fields = ['fecha']
    ordering = ['-fecha']
    queryset = LogAuditoria.objects.select_related('usuario').all()
