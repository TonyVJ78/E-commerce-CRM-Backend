"""
Vistas de CU-35: endpoints de Machine Learning.

Todos los endpoints exigen autenticación JWT y aislamiento estricto por tienda.
Un usuario de empresa solo puede consultar predicciones de su(s) propia(s)
tienda(s). Los clientes solo ven sus propias predicciones de compra.
"""

from datetime import date

from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tiendas.models import Tienda
from apps.usuarios.permissions import IsEmpresaUser

from .models import (
    EntrenamientoModelo,
    PrediccionCompra,
    PrediccionVenta,
    RiesgoAbandono,
)
from .permissions import TiendaAisladaPermission
from .serializers import (
    EntrenamientoModeloSerializer,
    PrediccionCompraSerializer,
    PrediccionVentaSerializer,
    PronosticarVentasInputSerializer,
    RiesgoAbandonoSerializer,
    RiesgoAbandonoInputSerializer,
    PrediccionCompraInputSerializer,
    EntrenarModeloInputSerializer,
)

from .services.ventas import pronosticar_ventas
from .services.abandono import evaluar_riesgo_abandono
from .services.compras import predecir_compra


def _persistir_ventas(tienda, resultado):
    """Guarda una fila por día pronosticado, solo para resultados completos."""
    if resultado.get('estado') != 'completado':
        return 0
    metrica = resultado.get('metrica') or {}
    registros = [
        PrediccionVenta(
            tienda=tienda,
            periodo_inicio=date.fromisoformat(resultado['periodo_inicio']),
            periodo_fin=date.fromisoformat(resultado['periodo_fin']),
            horizonte_dias=resultado['horizonte_dias'],
            valor_previsto=prediccion['valor_previsto'],
            mae=metrica.get('mae'),
            rmse=metrica.get('rmse'),
        )
        for prediccion in resultado.get('fechas_previstas', [])
    ]
    PrediccionVenta.objects.bulk_create(registros)
    return len(registros)


def _persistir_abandono(tienda, resultado):
    if resultado.get('estado') != 'completado':
        return 0
    registros = [
        RiesgoAbandono(
            tienda=tienda,
            cliente_id=cliente['cliente_id'],
            probabilidad_abandono=cliente['probabilidad_abandono'],
            nivel_riesgo=cliente['nivel_riesgo'],
        )
        for cliente in resultado.get('clientes', [])
    ]
    RiesgoAbandono.objects.bulk_create(registros)
    return len(registros)


def _persistir_compra(tienda, cliente_id, resultado):
    if resultado.get('estado') != 'completado':
        return 0
    PrediccionCompra.objects.create(
        tienda=tienda,
        cliente_id=cliente_id,
        probabilidad_compra=resultado['probabilidad_compra'],
        horizonte_dias=resultado['horizonte_dias'],
    )
    return 1


class PronosticarVentasView(APIView):
    """POST /api/ml/ventas/pronosticar/

    Ejecuta un pronóstico de ventas para la tienda indicada.
    Solo usuarios con rol empresa sobre su propia tienda.
    """
    permission_classes = [permissions.IsAuthenticated, IsEmpresaUser, TiendaAisladaPermission]

    def post(self, request):
        serializer = PronosticarVentasInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tienda_id = serializer.validated_data['tienda_id']
        horizonte = serializer.validated_data.get('horizonte_dias', 7)
        tienda = get_object_or_404(Tienda, pk=tienda_id)

        # Aislamiento: la tienda debe pertenecer al usuario autenticado
        if tienda.propietario_id != request.user.id:
            return Response(
                {'detail': 'No tiene permiso para pronosticar esta tienda.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        resultado = pronosticar_ventas(tienda=tienda, horizonte_dias=horizonte)
        resultado['registros_persistidos'] = _persistir_ventas(tienda, resultado)
        return Response(resultado, status=status.HTTP_200_OK)


class ListarPronosticosVentaView(APIView):
    """GET /api/ml/ventas/pronosticos/

    Lista los pronósticos de venta guardados de la tienda del usuario.
    """
    permission_classes = [permissions.IsAuthenticated, IsEmpresaUser, TiendaAisladaPermission]

    def get(self, request):
        tienda_id = request.query_params.get('tienda_id')
        qs = PrediccionVenta.objects.all()
        if tienda_id:
            tienda = get_object_or_404(Tienda, pk=tienda_id)
            if tienda.propietario_id != request.user.id:
                return Response(
                    {'detail': 'No tiene permiso para consultar esta tienda.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            qs = qs.filter(tienda=tienda)
        else:
            qs = qs.filter(tienda__propietario=request.user)
        data = PrediccionVentaSerializer(qs, many=True).data
        return Response(data, status=status.HTTP_200_OK)


class EvaluarRiesgoAbandonoView(APIView):
    """POST /api/ml/clientes/riesgo-abandono/

    Evalúa el riesgo de abanduno de clientes de una tienda.
    """
    permission_classes = [permissions.IsAuthenticated, IsEmpresaUser, TiendaAisladaPermission]

    def post(self, request):
        serializer = RiesgoAbandonoInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tienda_id = serializer.validated_data['tienda_id']
        umbral = serializer.validated_data.get('dias_umbral_abandono', 90)
        tienda = get_object_or_404(Tienda, pk=tienda_id)

        if tienda.propietario_id != request.user.id:
            return Response(
                {'detail': 'No tiene permiso para evaluar esta tienda.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        resultado = evaluar_riesgo_abandono(tienda=tienda, dias_umbral_abandono=umbral)
        resultado['registros_persistidos'] = _persistir_abandono(tienda, resultado)
        return Response(resultado, status=status.HTTP_200_OK)


class ListarRiesgosAbandonoView(APIView):
    """GET /api/ml/clientes/riesgos-abandono/"""

    permission_classes = [permissions.IsAuthenticated, IsEmpresaUser, TiendaAisladaPermission]

    def get(self, request):
        tienda_id = request.query_params.get('tienda_id')
        qs = RiesgoAbandono.objects.all()
        if tienda_id:
            tienda = get_object_or_404(Tienda, pk=tienda_id)
            if tienda.propietario_id != request.user.id:
                return Response(
                    {'detail': 'No tiene permiso para consultar esta tienda.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            qs = qs.filter(tienda=tienda)
        else:
            qs = qs.filter(tienda__propietario=request.user)
        data = RiesgoAbandonoSerializer(qs, many=True).data
        return Response(data, status=status.HTTP_200_OK)


class PredecirCompraView(APIView):
    """POST /api/ml/compras/predecir/

    Predice la probabilidad de próxima compra de un cliente en una tienda.
    Empresa: puede consultar clientes de su tienda. Cliente: solo a sí mismo.
    """
    permission_classes = [permissions.IsAuthenticated, TiendaAisladaPermission]

    def post(self, request):
        serializer = PrediccionCompraInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tienda_id = serializer.validated_data['tienda_id']
        cliente_id = serializer.validated_data.get('cliente_id')
        horizonte = serializer.validated_data.get('horizonte_dias', 7)
        tienda = get_object_or_404(Tienda, pk=tienda_id)

        if tienda.propietario_id != request.user.id:
            # Si es cliente, solo puede consultar su propia predicción
            if not (
                request.user.rol and request.user.rol.nombre == 'cliente'
                and cliente_id == request.user.id
            ):
                return Response(
                    {'detail': 'No tiene permiso para predecir esta compra.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

        resultado = predecir_compra(
            tienda=tienda,
            cliente_id=cliente_id or request.user.id,
            horizonte_dias=horizonte,
        )
        resultado['registros_persistidos'] = _persistir_compra(
            tienda, cliente_id or request.user.id, resultado
        )
        return Response(resultado, status=status.HTTP_200_OK)


class ListarPrediccionesCompraView(APIView):
    """GET /api/ml/compras/predicciones/"""

    permission_classes = [permissions.IsAuthenticated, TiendaAisladaPermission]

    def get(self, request):
        tienda_id = request.query_params.get('tienda_id')
        qs = PrediccionCompra.objects.all()
        if tienda_id:
            tienda = get_object_or_404(Tienda, pk=tienda_id)
            if tienda.propietario_id != request.user.id:
                if not (
                    request.user.rol and request.user.rol.nombre == 'cliente'
                ):
                    return Response(
                        {'detail': 'No tiene permiso para consultar esta tienda.'},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                qs = qs.filter(tienda=tienda, cliente=request.user)
            else:
                qs = qs.filter(tienda=tienda)
        else:
            if request.user.rol and request.user.rol.nombre == 'empresa':
                qs = qs.filter(tienda__propietario=request.user)
            else:
                qs = qs.filter(cliente=request.user)
        data = PrediccionCompraSerializer(qs, many=True).data
        return Response(data, status=status.HTTP_200_OK)


class ListarEntrenamientosView(APIView):
    """GET /api/ml/entrenamientos/ — historial de entrenamientos del usuario."""

    permission_classes = [permissions.IsAuthenticated, IsEmpresaUser]

    def get(self, request):
        qs = EntrenamientoModelo.objects.filter(usuario_ejecutor=request.user)
        data = EntrenamientoModeloSerializer(qs, many=True).data
        return Response(data, status=status.HTTP_200_OK)
