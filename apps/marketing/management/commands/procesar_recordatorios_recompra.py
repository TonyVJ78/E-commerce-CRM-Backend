from datetime import timedelta
from statistics import median
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max
from django.db import transaction
from django.contrib.auth import get_user_model
from apps.marketing.models import NotificacionEnviada
from django.utils import timezone
from apps.pedidos.models import ItemPedido
from apps.marketing.notificaciones import crear_notificacion


class Command(BaseCommand):
    help = 'Recordatorios de compras entregadas, ventana 15–60 días y pausa de 7 días por tienda/cliente.'

    def add_arguments(self, parser):
        parser.add_argument('--dias', type=int, default=settings.RECOMPRA_DIAS)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opts):
        if not 15 <= opts['dias'] <= settings.RECOMPRA_MAX_DIAS:
            raise CommandError('--dias debe estar entre 15 y RECOMPRA_MAX_DIAS.')
        base = ItemPedido.objects.filter(pedido__estado_actual='entregado',
            pedido__cliente__is_active=True, pedido__cliente__activo=True, pedido__cliente__rol__nombre='cliente',
            tienda__activa=True, variante__producto__activo=True)
        grupos = base.values('pedido__cliente_id', 'tienda_id', 'variante__producto_id').annotate(ultima=Max('pedido__fecha'))
        total = 0
        for g in grupos.iterator():
            compras = base.filter(pedido__cliente_id=g['pedido__cliente_id'], tienda_id=g['tienda_id'],
                variante__producto_id=g['variante__producto_id']).select_related('pedido__cliente', 'tienda', 'variante__producto')
            fechas = sorted(set(compras.values_list('pedido__fecha', flat=True)), reverse=True)[:6]
            intervalos = [(a-b).days for a, b in zip(fechas, fechas[1:]) if (a-b).days > 0]
            dias = max(15, min(settings.RECOMPRA_MAX_DIAS, round(median(intervalos)))) if intervalos else opts['dias']
            if g['ultima'] + timedelta(days=dias) > timezone.now():
                continue
            # A more recent purchase, including one still awaiting delivery, suppresses the old reminder.
            if ItemPedido.objects.filter(pedido__cliente_id=g['pedido__cliente_id'], tienda_id=g['tienda_id'],
                variante__producto_id=g['variante__producto_id'], pedido__fecha__gt=g['ultima']).exclude(
                    pedido__estado_actual='cancelado').exists():
                continue
            if g['ultima'] < timezone.now()-timedelta(days=settings.RECOMPRA_MAX_DIAS):
                continue
            if NotificacionEnviada.objects.filter(cliente_id=g['pedido__cliente_id'], tienda_id=g['tienda_id'],
                fecha__gte=timezone.now()-timedelta(days=settings.RECOMPRA_COOLDOWN_DIAS),
                tipo__in=['recompra', 'recordatorio_recompra']).exists():
                continue
            item = compras.order_by('-pedido__fecha').first()
            producto = item.variante.producto
            if not producto.variantes.filter(activa=True, stock__gt=0).exists():
                continue
            clave = f"recompra:{item.pedido.cliente_id}:{item.tienda_id}:{producto.pk}:{g['ultima'].isoformat()}"
            if opts['dry_run']:
                total += not NotificacionEnviada.objects.filter(clave_evento=clave).exists()
                continue
            with transaction.atomic():
                get_user_model().objects.select_for_update().get(pk=item.pedido.cliente_id)
                if NotificacionEnviada.objects.filter(cliente_id=item.pedido.cliente_id, tienda=item.tienda,
                    fecha__gte=timezone.now()-timedelta(days=settings.RECOMPRA_COOLDOWN_DIAS),
                    tipo__in=['recompra', 'recordatorio_recompra']).exists():
                    continue
                _, creada = crear_notificacion(tienda=item.tienda, cliente=item.pedido.cliente,
                    titulo='¿Necesitas reponer tu compra?', mensaje=f'Vuelve a consultar {producto.nombre} en {item.tienda.nombre}.',
                    tipo='recompra', datos={'producto_id': producto.pk}, clave=clave)
                total += creada
        self.stdout.write(f'Recordatorios {"previstos" if opts["dry_run"] else "creados"}: {total}')
