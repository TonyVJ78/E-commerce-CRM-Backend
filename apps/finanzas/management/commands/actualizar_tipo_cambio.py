from django.core.management.base import BaseCommand, CommandError

from apps.finanzas.tipo_cambio import (
    DIAS_ACTUALIZACION,
    LIMITE_HISTORIAL,
    actualizar_tipo_cambio,
    tipo_cambio_vigente,
)


class Command(BaseCommand):
    help = 'Descarga el tipo de cambio oficial (BCB, vía factura.bo) y lo guarda por fecha.'

    def add_arguments(self, parser):
        parser.add_argument('--solo-brl', action='store_true', help='BRL indicativo: requiere aprobación y política explícitas; nunca actualiza USD.')
        parser.add_argument(
            '--historial',
            type=int,
            default=DIAS_ACTUALIZACION,
            help=f'Días a descargar, de 1 a {LIMITE_HISTORIAL} (365 carga el último año).',
        )

    def handle(self, *args, **options):
        if options.get('solo_brl'):
            from apps.finanzas.brl import actualizar_brl
            resultado = actualizar_brl()
            if resultado['estado'] not in ('guardada', 'sin_cambios'):
                raise CommandError(f"BRL no actualizado: {resultado['estado']}")
            self.stdout.write(self.style.SUCCESS(f"BRL: {resultado['estado']}"))
            return
        dias = options['historial']
        if not 1 <= dias <= LIMITE_HISTORIAL:
            raise CommandError(f'--historial debe estar entre 1 y {LIMITE_HISTORIAL}.')

        guardadas = actualizar_tipo_cambio(dias)
        if guardadas is None:
            raise CommandError('No se pudo obtener el tipo de cambio; revisa el log.')

        vigente = tipo_cambio_vigente()
        self.stdout.write(self.style.SUCCESS(
            f'{guardadas} cotizaciones guardadas. Vigente: {vigente}.'
        ))
