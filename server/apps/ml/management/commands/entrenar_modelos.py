"""
Comando de entrenamiento de modelos CU-35.

Ejemplo de uso (solo desarrollo local, NO en producción de Neon):
    python manage.py entrenar_modelos --tipo ventas --tienda-id 1 --usuario-id 1
    python manage.py entrenar_modelos --tipo abandono --tienda-id 1 --usuario-id 1
    python manage.py entrenar_modelos --tipo compras --tienda-id 1 --usuario-id 1

Este comando ejecuta el entrenamiento e inferece sobre la tienda indicada y
guarda un registro trazable en la tabla ml_entrenamiento_modelo. No realiza
entrenamiento pesado dentro de solicitudes HTTP de Vercel.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.tiendas.models import Tienda
from apps.usuarios.models import Usuario

from apps.ml.services.ventas import pronosticar_ventas
from apps.ml.services.abandono import evaluar_riesgo_abandono
from apps.ml.services.compras import predecir_compra
from apps.ml.models import EntrenamientoModelo


def _registro_entrenamiento(tipo_modelo, tienda, usuario, resultado):
    """Crea un registro de entrenamiento a partir del resultado del servicio."""
    estado = EntrenamientoModelo.ESTADO_COMPLETADO
    if resultado.get('estado') == 'datos_insuficientes':
        estado = EntrenamientoModelo.ESTADO_INSUFICIENTE
    elif resultado.get('estado') == 'error':
        estado = EntrenamientoModelo.ESTADO_FALLIDO

    metricas = {}
    if resultado.get('metrica'):
        metricas = resultado['metrica']

    return EntrenamientoModelo.objects.create(
        tipo_modelo=tipo_modelo,
        estado=estado,
        metricas=metricas,
        fecha_inicio=timezone.now(),
        fecha_fin=timezone.now(),
        usuario_ejecutor=usuario,
    )


class Command(BaseCommand):
    help = 'Entrena modelos de ML de CU-35 para una tienda (local/worker).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tipo',
            type=str,
            choices=['ventas', 'abandono', 'compras'],
            required=True,
            help='Tipo de modelo a entrenar',
        )
        parser.add_argument(
            '--tienda-id',
            type=int,
            required=True,
            help='ID de la tienda',
        )
        parser.add_argument(
            '--usuario-id',
            type=int,
            required=True,
            help='ID del usuario ejecutor',
        )

    def handle(self, *args, **options):
        tipo = options['tipo']
        tienda_id = options['tienda_id']
        usuario_id = options['usuario_id']

        try:
            tienda = Tienda.objects.get(pk=tienda_id)
        except Tienda.DoesNotExist:
            self.stderr.write(f'Tienda {tienda_id} no existe.')
            return

        try:
            usuario = Usuario.objects.get(pk=usuario_id)
        except Usuario.DoesNotExist:
            self.stderr.write(f'Usuario {usuario_id} no existe.')
            return

        if tienda.propietario_id != usuario.id:
            self.stderr.write(
                'El usuario no es propietario de esta tienda.'
            )
            return

        self.stdout.write(f'Entrenando modelo "{tipo}" para tienda {tienda.id}...')

        try:
            if tipo == 'ventas':
                resultado = pronosticar_ventas(tienda=tienda, horizonte_dias=7)
            elif tipo == 'abandono':
                resultado = evaluar_riesgo_abandono(tienda=tienda, dias_umbral_abandono=90)
            elif tipo == 'compras':
                # Predicción para el propio usuario si es cliente, o para todos
                # Si es empresa, no hay un cliente único; se omite predicción individual
                resultado = {
                    'estado': 'datos_insuficientes',
                    'mensaje': 'El modelo de compras requiere un cliente_id específico.',
                    'metrica': None,
                }
            else:
                resultado = {'estado': 'error', 'mensaje': 'Tipo no soportado'}

            registro = _registro_entrenamiento(tipo, tienda, usuario, resultado)
            self.stdout.write(
                self.style.SUCCESS(
                    f'Entrenamiento {registro.id}: {registro.tipo_modelo} - '
                    f'{registro.estado}'
                )
            )
            self.stdout.write(f'Métricas: {registro.metricas}')

        except Exception as exc:  # noqa: BLE001
            EntrenamientoModelo.objects.create(
                tipo_modelo=tipo,
                estado=EntrenamientoModelo.ESTADO_FALLIDO,
                metricas={'error': str(exc)},
                fecha_inicio=timezone.now(),
                fecha_fin=timezone.now(),
                usuario_ejecutor=usuario,
            )
            self.stderr.write(f'Error durante el entrenamiento: {exc}')
