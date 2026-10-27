from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.marketing.models import Cupon
from apps.marketing.notificaciones import notificar_cupon


class Command(BaseCommand):
    help = 'Publica promociones vigentes, incluidas las programadas para hoy; no repite destinatarios.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opts):
        hoy = timezone.localdate()
        total = sum(notificar_cupon(c, dry_run=opts['dry_run']) for c in Cupon.objects.filter(activo=True,
            fecha_inicio__lte=hoy, fecha_expiracion__gte=hoy).select_related('tienda', 'campana'))
        self.stdout.write(f'Promociones notificadas: {total}')
