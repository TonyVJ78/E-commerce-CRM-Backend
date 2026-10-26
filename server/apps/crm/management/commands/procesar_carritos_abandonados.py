"""
Comando de gestión de Django para el procesamiento y notificación de carritos abandonados (CU-27).
Ejecución: python manage.py procesar_carritos_abandonados
"""

from decimal import Decimal
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils import timezone

from apps.crm.models import CampanaCarrito, RegistroRecuperacionCarrito
from apps.pedidos.models import Carrito, Pedido


class Command(BaseCommand):
    help = 'Evalua carritos inactivos segun las campanas activas y envia correos de recuperacion.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula la ejecucion sin enviar correos ni registrar en base de datos.',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        self.stdout.write('[CRON] Iniciando evaluacion de carritos abandonados...')

        campanas_activas = CampanaCarrito.objects.filter(activo=True).select_related('tienda')
        total_evaluadas = campanas_activas.count()

        if total_evaluadas == 0:
            self.stdout.write('[INFO] No hay campanas de carrito abandonado activas en este momento.')
            return

        total_notificados = 0
        total_carritos_evaluados = 0

        for campana in campanas_activas:
            tienda = campana.tienda
            tiempo_limite = timezone.now() - timezone.timedelta(hours=campana.horas_inactividad)

            # Buscar carritos con fecha menor o igual al umbral de inactividad
            carritos = (
                Carrito.objects.filter(tienda=tienda, ultima_actividad__lte=tiempo_limite)
                .select_related('cliente')
                .prefetch_related('items', 'items__variante', 'items__variante__producto')
                .distinct()
            )

            for carrito in carritos:
                if RegistroRecuperacionCarrito.objects.filter(
                    campana=campana, carrito=carrito, correo_enviado=True,
                    fecha_envio__gte=carrito.ultima_actividad,
                ).exists():
                    continue

                items = list(carrito.items.all())
                if not items:
                    continue

                total_carritos_evaluados += 1

                # Verificar si el cliente ya completo un pedido posterior en esta tienda
                pedido_posterior = Pedido.objects.filter(
                    cliente=carrito.cliente,
                    tienda=tienda,
                    fecha__gte=carrito.ultima_actividad,
                ).exists()

                if pedido_posterior:
                    continue

                # Calcular total y detalles de los items
                monto_total = sum(
                    Decimal(str(it.variante.precio)) * Decimal(str(it.cantidad)) for it in items
                )

                destinatario = carrito.cliente.email
                if not destinatario:
                    continue

                cliente_nombre = f"{carrito.cliente.first_name} {carrito.cliente.last_name}".strip() or "estimado cliente"

                # Construir contenido del correo
                asunto = campana.asunto_email
                cupon_html = ""
                if campana.descuento_porcentaje > 0:
                    cupon_html = f"""
                    <div style="background:#FFF8DB;border:1px solid #F5B301;padding:12px 16px;border-radius:8px;margin:16px 0;">
                        <p style="margin:0;color:#1B1D24;font-weight:700;">
                            Descuento especial del {campana.descuento_porcentaje}% reservado para ti
                        </p>
                        <p style="margin:4px 0 0;color:#5F6675;font-size:14px;">
                            Ingresa el cupon: <strong>{campana.codigo_cupon or 'RECUPERA'}</strong> al finalizar tu compra.
                        </p>
                    </div>
                    """

                items_html = "".join([
                    f"<li style='margin-bottom:6px;'>{it.cantidad}x {it.variante.producto.nombre} ({it.variante.nombre}) - Bs {it.variante.precio}</li>"
                    for it in items
                ])

                cuerpo_html = f"""
                <!DOCTYPE html>
                <html lang="es">
                <head><meta charset="utf-8"></head>
                <body style="font-family:'Segoe UI',Roboto,sans-serif;color:#1B1D24;background:#F6F7FA;padding:24px;margin:0;">
                    <div style="max-width:560px;margin:0 auto;background:#FFFFFF;border-radius:12px;border:1px solid #E2E4E9;padding:32px;">
                        <h2 style="color:#C8102E;margin:0 0 12px 0;">Kantu Market - {tienda.nombre}</h2>
                        <p style="font-size:15px;color:#3A3F4B;">Hola {cliente_nombre},</p>
                        <p style="font-size:15px;color:#3A3F4B;line-height:1.5;">{campana.mensaje_email}</p>
                        {cupon_html}
                        <div style="background:#F6F7FA;padding:16px;border-radius:8px;margin:16px 0;">
                            <strong style="display:block;margin-bottom:8px;color:#1B1D24;">Tus productos guardados:</strong>
                            <ul style="margin:0;padding-left:20px;color:#5F6675;font-size:14px;">
                                {items_html}
                            </ul>
                            <p style="margin:12px 0 0 0;font-weight:700;color:#1B1D24;">Total: Bs {monto_total:.2f}</p>
                        </div>
                        <div style="text-align:center;margin-top:24px;">
                            <a href="{settings.FRONTEND_URL.rstrip('/')}/carrito" style="display:inline-block;background:#C8102E;color:#FFFFFF;text-decoration:none;font-weight:600;padding:12px 24px;border-radius:8px;">
                                Volver al Carrito y Comprar
                            </a>
                        </div>
                    </div>
                </body>
                </html>
                """

                if not dry_run:
                    try:
                        send_mail(
                            subject=asunto,
                            message=campana.mensaje_email,
                            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@kantu.bo'),
                            recipient_list=[destinatario],
                            html_message=cuerpo_html,
                            fail_silently=False,
                        )

                        registro = RegistroRecuperacionCarrito.objects.filter(
                            campana=campana, carrito=carrito, fecha_envio__gte=carrito.ultima_actividad).first()
                        if registro:
                            registro.correo_enviado = True
                            registro.save(update_fields=['correo_enviado'])
                        else:
                            RegistroRecuperacionCarrito.objects.create(
                                campana=campana, carrito=carrito, cliente=carrito.cliente, correo_enviado=True)
                        total_notificados += 1
                        self.stdout.write(
                            f"[NOTIFICADO] Carrito #{carrito.id} en tienda #{tienda.id}"
                        )
                    except Exception as e:
                        self.stderr.write(
                            f"[ERROR] No se pudo enviar email del carrito #{carrito.id}"
                        )
                else:
                    total_notificados += 1
                    self.stdout.write(
                        f"[DRY-RUN] Se habria notificado Carrito #{carrito.id} en tienda #{tienda.id}"
                    )

        self.stdout.write(
            f"[FIN] Proceso completado. Carritos evaluados: {total_carritos_evaluados}. Notificaciones enviadas: {total_notificados}."
        )
