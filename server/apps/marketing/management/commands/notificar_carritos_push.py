from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from apps.crm.models import CampanaCarrito, RegistroRecuperacionCarrito
from apps.pedidos.models import Carrito, Pedido
from apps.marketing.notificaciones import crear_notificacion
from apps.marketing.models import NotificacionEnviada


class Command(BaseCommand):
    help = 'Bandeja/push para campañas de carrito; no modifica métricas de correo.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opts):
        total = 0
        for campana in CampanaCarrito.objects.filter(activo=True, tienda__activa=True).select_related('tienda'):
            limite = timezone.now()-timedelta(hours=campana.horas_inactividad)
            for c in Carrito.objects.filter(tienda=campana.tienda, ultima_actividad__lte=limite,
                cliente__is_active=True, cliente__activo=True, cliente__rol__nombre='cliente').select_related('cliente'):
                if not c.items.exists() or Pedido.objects.filter(cliente=c.cliente, tienda=c.tienda,
                    fecha__gte=c.ultima_actividad).exclude(estado_actual='cancelado').exists():
                    continue
                clave = f'carrito:{c.pk}:{c.ultima_actividad.isoformat()}'
                if opts['dry_run']:
                    total += not NotificacionEnviada.objects.filter(clave_evento=clave).exists()
                    continue
                productos = ', '.join(c.items.values_list('variante__producto__nombre', flat=True)[:3])
                with transaction.atomic():
                    # Same lock/order as checkout: never record a reminder after checkout emptied this cart.
                    c = Carrito.objects.select_for_update().get(pk=c.pk)
                    if c.ultima_actividad > limite or not c.items.exists():
                        continue
                    clave = f'carrito:{c.pk}:{c.ultima_actividad.isoformat()}'
                    _, creada = crear_notificacion(tienda=campana.tienda, cliente=c.cliente,
                        titulo=campana.asunto_email, mensaje=f'{campana.mensaje_email} Productos: {productos}',
                        tipo='carrito_abandonado', datos={'carrito_id': c.pk}, clave=clave)
                    if creada and not RegistroRecuperacionCarrito.objects.filter(
                        campana=campana, carrito=c, fecha_envio__gte=c.ultima_actividad).exists():
                        RegistroRecuperacionCarrito.objects.create(campana=campana, carrito=c,
                            cliente=c.cliente, correo_enviado=False)
                    total += creada
        self.stdout.write(f'Carritos {"previstos" if opts["dry_run"] else "notificados"}: {total}')
