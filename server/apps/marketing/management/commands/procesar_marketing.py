from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Tarea periódica CU26–CU28: correo, bandeja, push y promociones programadas.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opts):
        for job in ('notificar_carritos_push', 'procesar_carritos_abandonados',
                    'procesar_promociones', 'procesar_recordatorios_recompra'):
            call_command(job, dry_run=opts['dry_run'], stdout=self.stdout, stderr=self.stderr)
