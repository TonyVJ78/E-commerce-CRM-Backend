"""
Vistas del módulo de Tiendas.
Sprint 0 & CU10: Crear y listar tiendas del usuario autenticado, dashboard del vendedor.
CU13: Gestión de identidad de marca (logo, color primario, slug).
"""

import logging

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from rest_framework import generics, permissions, status
from rest_framework.exceptions import APIException
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalogo.services import CloudinaryConfigurationError, CloudinaryUploadError
from apps.usuarios.audit import AuditoriaCreateMixin, AuditoriaUpdateMixin
from apps.usuarios.permissions import IsEmpresaUser

from .models import Tienda
from .serializers import TiendaIdentidadSerializer, TiendaSerializer, PanelTiendaSerializer
from .services import consultar_alertas_stock, consultar_panel_tienda, resolver_tienda_autorizada


logger = logging.getLogger(__name__)


class ControlledErrorMixin:
    """Conserva errores DRF esperados y oculta detalles de fallos inesperados."""

    def handle_exception(self, exc):
        if isinstance(exc, (APIException, Http404, PermissionDenied)):
            return super().handle_exception(exc)
        logger.exception('Error inesperado en el endpoint de identidad de marca')
        return Response(
            {'detail': 'No se pudo procesar la identidad de marca.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
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


class TiendaIdentidadView(
    ControlledErrorMixin,
    AuditoriaUpdateMixin,
    generics.RetrieveUpdateAPIView,
):
    """
    GET/PATCH /api/tiendas/<pk>/identidad/
    Gestión de identidad de marca multitenant (CU-13).
    Aislamiento estricto: valida que request.user == tienda.propietario.
    """
    serializer_class = TiendaIdentidadSerializer
    permission_classes = [permissions.IsAuthenticated, IsEmpresaUser]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ['get', 'patch', 'head', 'options']
    audit_tabla = 'tienda'

    def get_queryset(self):
        return Tienda.objects.filter(propietario=self.request.user)

    def get_object(self):
        tienda = get_object_or_404(Tienda, pk=self.kwargs['pk'])
        if tienda.propietario_id != self.request.user.id:
            raise PermissionDenied('No tienes permiso para acceder o modificar la identidad de esta tienda.')
        return tienda

    @transaction.atomic
    def perform_update(self, serializer):
        if serializer.instance.propietario_id != self.request.user.id:
            raise PermissionDenied('No tienes permiso para modificar la identidad de esta tienda.')
        super().perform_update(serializer)

    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except (CloudinaryConfigurationError, CloudinaryUploadError) as exc:
            return Response(
                {'logo': [str(exc)]},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class SlugDisponibilidadView(ControlledErrorMixin, APIView):
    """
    GET /api/tiendas/<pk>/identidad/slug-disponible/?slug=mi-tienda
    Comprueba disponibilidad sin sustituir la validación del PATCH.
    Aislamiento estricto: valida que request.user == tienda.propietario.
    """
    permission_classes = [permissions.IsAuthenticated, IsEmpresaUser]

    def get(self, request, pk):
        tienda = get_object_or_404(Tienda, pk=pk)
        if tienda.propietario_id != request.user.id:
            raise PermissionDenied('No tienes permiso para consultar esta tienda.')

        slug = slugify(request.query_params.get('slug', ''))
        if not slug:
            return Response(
                {'slug': ['Ingresa un slug válido.']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(slug) > 100:
            return Response(
                {'slug': ['El slug no puede superar los 100 caracteres.']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        disponible = not Tienda.objects.filter(slug=slug).exclude(pk=tienda.pk).exists()
        return Response({'slug': slug, 'disponible': disponible})


class DashboardVendedorView(APIView):
    """
    CU-17/CU-18: resumen operativo de una tienda del propietario autenticado.
    La ruta anterior acepta tienda_id; sin él solo resuelve una tienda única.
    """
    permission_classes = [permissions.IsAuthenticated, IsEmpresaUser]

    def get(self, request, tienda_id=None):
        tienda_id = tienda_id or request.query_params.get('tienda_id')
        tienda = resolver_tienda_autorizada(request.user, tienda_id)
        return Response(PanelTiendaSerializer(consultar_panel_tienda(tienda)).data)


class AlertaStockView(APIView):
    """GET /api/tiendas/<tienda_id>/alertas-stock/ — Alertas vigentes, sin duplicados."""
    permission_classes = [permissions.IsAuthenticated, IsEmpresaUser]

    def get(self, request, tienda_id):
        tienda = resolver_tienda_autorizada(request.user, tienda_id)
        alertas = consultar_alertas_stock(tienda)
        return Response({'tienda_id': tienda.id, 'cantidad': len(alertas), 'alertas_stock': alertas})
