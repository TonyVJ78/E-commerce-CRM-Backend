"""
Controladores REST API para CU-27: Configurar campaña de carrito abandonado
(Recuperación de ventas y fidelización multitenant).
"""

from decimal import Decimal
from django.conf import settings
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.crm.models import CampanaCarrito, RegistroRecuperacionCarrito
from apps.crm.serializers import CampanaCarritoSerializer
from apps.tiendas.models import Tienda
from apps.pedidos.models import Carrito
from apps.usuarios.permissions import IsEmpresa
from apps.usuarios.audit import ACCION_ACTUALIZAR, registrar_auditoria


def _get_tienda_vendedor(request, tienda_id):
    """Verifica permisos de tienda para el vendedor o superusuario."""
    if getattr(request.user, 'is_superuser', False):
        return get_object_or_404(Tienda, pk=tienda_id)
    return get_object_or_404(Tienda, pk=tienda_id, propietario=request.user)


def _get_or_create_campana(tienda):
    """Obtiene la campana de la tienda o inicializa una con parametros por defecto."""
    campana, _ = CampanaCarrito.objects.get_or_create(
        tienda=tienda,
        defaults={
            'activo': False,
            'horas_inactividad': 2,
            'asunto_email': f'¡Tienes productos esperándote en {tienda.nombre}!',
            'mensaje_email': (
                f'Hola. Notamos que dejaste artículos seleccionados en {tienda.nombre}. '
                f'Aprovecha de completar tu pedido antes de que se agote el stock disponible.'
            ),
            'descuento_porcentaje': 0,
            'codigo_cupon': '',
        },
    )
    return campana


class TiendaCampanaCarritoView(APIView):
    """
    GET /api/tiendas/<tienda_id>/campana-carrito/
    PUT/PATCH /api/tiendas/<tienda_id>/campana-carrito/
    Consulta y actualización de la campaña de carrito abandonado con resumen métrico.
    """
    permission_classes = [permissions.IsAuthenticated, IsEmpresa]

    def get(self, request, tienda_id):
        tienda = _get_tienda_vendedor(request, tienda_id)
        campana = _get_or_create_campana(tienda)

        # Cálculo de métricas
        limite_tiempo = timezone.now() - timezone.timedelta(hours=campana.horas_inactividad)
        carritos_queryset = (
            Carrito.objects.filter(tienda=tienda, ultima_actividad__lte=limite_tiempo)
            .prefetch_related('items', 'items__variante')
            .distinct()
        )

        carritos_detectados = 0
        valor_en_riesgo = Decimal('0.00')

        for carrito in carritos_queryset:
            items = carrito.items.all()
            if items:
                carritos_detectados += 1
                for it in items:
                    valor_en_riesgo += Decimal(str(it.variante.precio)) * Decimal(str(it.cantidad))

        registros = RegistroRecuperacionCarrito.objects.filter(campana=campana)
        emails_enviados = registros.filter(correo_enviado=True).count()
        total_notificados = registros.count()
        carritos_recuperados = registros.filter(recuperado=True).count()

        tasa_conversion = (
            round((carritos_recuperados / total_notificados) * 100, 1)
            if total_notificados > 0
            else 0.0
        )

        resumen = {
            'carritos_detectados': carritos_detectados,
            'valor_en_riesgo': float(valor_en_riesgo),
            'emails_enviados': emails_enviados,
            'carritos_recuperados': carritos_recuperados,
            'tasa_conversion': tasa_conversion,
        }

        serializer = CampanaCarritoSerializer(campana)
        return Response({
            'campana': serializer.data,
            'metricas': resumen,
        }, status=status.HTTP_200_OK)

    def put(self, request, tienda_id):
        return self._guardar(request, tienda_id)

    def patch(self, request, tienda_id):
        return self._guardar(request, tienda_id, partial=True)

    def _guardar(self, request, tienda_id, partial=False):
        tienda = _get_tienda_vendedor(request, tienda_id)
        campana = _get_or_create_campana(tienda)

        serializer = CampanaCarritoSerializer(campana, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        datos_anteriores = {
            'activo': campana.activo,
            'horas_inactividad': campana.horas_inactividad,
            'descuento_porcentaje': campana.descuento_porcentaje,
            'codigo_cupon': campana.codigo_cupon,
        }

        campana_actualizada = serializer.save()

        # Registro en auditoría (CU-23)
        registrar_auditoria(
            request,
            ACCION_ACTUALIZAR,
            tabla='campana_carrito',
            registro_id=campana_actualizada.id,
            datos_anteriores=datos_anteriores,
            datos_nuevos=serializer.data,
        )

        return Response({
            'mensaje': 'Configuración de campaña guardada correctamente.',
            'campana': serializer.data,
        }, status=status.HTTP_200_OK)


class TiendaCarritosAbandonadosListView(APIView):
    """
    GET /api/tiendas/<tienda_id>/carritos-abandonados/
    Lista detallada de carritos inactivos detectados con productos de la tienda.
    """
    permission_classes = [permissions.IsAuthenticated, IsEmpresa]

    def get(self, request, tienda_id):
        tienda = _get_tienda_vendedor(request, tienda_id)
        campana = _get_or_create_campana(tienda)

        carritos = (
            Carrito.objects.filter(tienda=tienda, ultima_actividad__lte=(
                timezone.now() - timezone.timedelta(hours=campana.horas_inactividad)))
            .select_related('cliente')
            .prefetch_related(
                'items',
                'items__variante',
                'items__variante__producto',
                'registros_recuperacion',
            )
            .order_by('-fecha_creacion')
        )

        resultado = []
        for c in carritos:
            items_carrito = c.items.all()
            if not items_carrito:
                continue

            total_monto = Decimal('0.00')
            items_dto = []
            for item in items_carrito:
                subtotal = Decimal(str(item.variante.precio)) * Decimal(str(item.cantidad))
                total_monto += subtotal
                imgs = item.variante.producto.imagenes or []
                img_url = imgs[0] if imgs else None

                items_dto.append({
                    'id': item.id,
                    'producto_nombre': item.variante.producto.nombre,
                    'variante': item.variante.nombre,
                    'cantidad': item.cantidad,
                    'precio_unitario': float(item.variante.precio),
                    'subtotal': float(subtotal),
                    'imagen': img_url,
                })

            horas_inactivo = max(
                0.1,
                round((timezone.now() - c.ultima_actividad).total_seconds() / 3600, 1)
            )

            notificacion = c.registros_recuperacion.filter(
                campana=campana, fecha_envio__gte=c.ultima_actividad).order_by('-fecha_envio').first()

            cliente_nombre = f"{c.cliente.first_name} {c.cliente.last_name}".strip() or c.cliente.email

            resultado.append({
                'id': c.id,
                'cliente': {
                    'id': c.cliente.id,
                    'email': c.cliente.email,
                    'nombre': cliente_nombre,
                },
                'fecha_creacion': c.fecha_creacion.isoformat(),
                'horas_inactivo': horas_inactivo,
                'total_items': sum(it['cantidad'] for it in items_dto),
                'monto_total': float(total_monto),
                'items': items_dto,
                'notificado': notificacion is not None,
                'fecha_notificacion': notificacion.fecha_envio.isoformat() if notificacion else None,
                'recuperado': notificacion.recuperado if notificacion else False,
            })

        return Response(resultado, status=status.HTTP_200_OK)


class TiendaDispararPruebaCampanaView(APIView):
    """
    POST /api/tiendas/<tienda_id>/campana-carrito/disparar-prueba/
    Envía un correo de prueba de la campaña a la dirección de correo de la tienda.
    """
    permission_classes = [permissions.IsAuthenticated, IsEmpresa]

    def post(self, request, tienda_id):
        tienda = _get_tienda_vendedor(request, tienda_id)
        campana = _get_or_create_campana(tienda)

        destinatario = tienda.propietario.email or request.user.email
        asunto = f"[PRUEBA] {campana.asunto_email}"

        descuento_html = ""
        if campana.descuento_porcentaje > 0:
            descuento_html = f"""
            <div style="background:#FFF8DB;border:1px solid #F5B301;padding:12px 16px;border-radius:8px;margin:16px 0;">
                <p style="margin:0;color:#1B1D24;font-weight:700;">
                    ¡Obtén un {campana.descuento_porcentaje}% de descuento en tu compra!
                </p>
                <p style="margin:4px 0 0;color:#5F6675;font-size:14px;">
                    Código de cupón: <strong>{campana.codigo_cupon or 'KANTU-RECUPERA'}</strong>
                </p>
            </div>
            """

        cuerpo_html = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head><meta charset="utf-8"></head>
        <body style="font-family:'Segoe UI',Roboto,sans-serif;color:#1B1D24;background:#F6F7FA;padding:24px;margin:0;">
            <div style="max-width:560px;margin:0 auto;background:#FFFFFF;border-radius:12px;border:1px solid #E2E4E9;padding:32px;box-shadow:0 2px 8px rgba(0,0,0,0.05);">
                <div style="text-align:center;margin-bottom:24px;">
                    <h2 style="color:#C8102E;margin:0;">Kantu Market</h2>
                    <p style="color:#5F6675;font-size:14px;margin:4px 0 0;">Mensaje de prueba de la tienda: {tienda.nombre}</p>
                </div>
                <div style="font-size:15px;line-height:1.6;color:#3A3F4B;">
                    <p>{campana.mensaje_email}</p>
                    {descuento_html}
                    <div style="text-align:center;margin-top:28px;">
                        <a href="http://localhost:4200/inicio" style="display:inline-block;background:#C8102E;color:#FFFFFF;text-decoration:none;font-weight:600;padding:12px 24px;border-radius:8px;">
                            Completar mi Pedido
                        </a>
                    </div>
                </div>
                <hr style="border:0;border-top:1px solid #E2E4E9;margin:28px 0 16px;">
                <p style="font-size:12px;color:#8A90A0;text-align:center;margin:0;">
                    Este es un correo simulado de verificación de plantilla de campaña de carritos abandonados.
                </p>
            </div>
        </body>
        </html>
        """

        try:
            send_mail(
                subject=asunto,
                message=campana.mensaje_email,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@kantu.bo'),
                recipient_list=[destinatario],
                html_message=cuerpo_html,
                fail_silently=False,
            )
            email_enviado = True
            mensaje_resultado = f"Correo de prueba enviado satisfactoriamente a {destinatario}."
        except Exception as e:
            email_enviado = False
            mensaje_resultado = f"Plantilla generada correctamente (simulada): {str(e)}"

        return Response({
            'success': True,
            'enviado': email_enviado,
            'destinatario': destinatario,
            'mensaje': mensaje_resultado,
        }, status=status.HTTP_200_OK)
