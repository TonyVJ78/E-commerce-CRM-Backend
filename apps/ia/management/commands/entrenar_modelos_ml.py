import time

from django.core.management.base import BaseCommand, CommandError

from apps.ia.ml.entrenamiento import entrenar_tienda
from apps.tiendas.models import Tienda


class Command(BaseCommand):
    help = 'Entrena los modelos de Machine Learning (pronóstico, abandono, compras conjuntas) de una tienda.'

    def add_arguments(self, parser):
        parser.add_argument('--tienda', type=int, required=True, help='ID de la tienda')

    def handle(self, *args, tienda, **opciones):
        try:
            instancia = Tienda.objects.get(pk=tienda)
        except Tienda.DoesNotExist:
            raise CommandError(f'No existe la tienda {tienda}.')

        inicio = time.perf_counter()
        omitidos = entrenar_tienda(instancia)
        segundos = time.perf_counter() - inicio

        for modelo in instancia.modelos_ml.order_by('tipo'):
            self.stdout.write(self.style.SUCCESS(f'{modelo.get_tipo_display()}: {modelo.algoritmo}'))
            self.stdout.write(f'  filas: {modelo.filas_entrenamiento}  métricas: {modelo.metricas}')
        for omitido in omitidos:
            self.stdout.write(self.style.WARNING(f'{omitido["titulo"]}: omitido. {omitido["motivo"]}'))
        self.stdout.write(f'Tiempo de entrenamiento: {segundos:.2f} s')
