"""
Siembra datos sintéticos de volumen para UNA empresa, en una tienda dedicada.

    python manage.py sembrar_datos_sinteticos --empresa empresa@kantu.bo
    python manage.py sembrar_datos_sinteticos --empresa empresa@kantu.bo --meses 12 --clientes 1200 \
        --pedidos 3000 --semilla 42 --reporte reporte_siembra.md
    python manage.py sembrar_datos_sinteticos --empresa empresa@kantu.bo --revertir

Nunca borra datos que no creó: `--revertir` elimina la tienda dedicada y los
clientes sintéticos de esa empresa (correos `e<id>-...@sintetico.kantu.bo`).
"""

import random
import time
from datetime import date, datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.crm.services.segmentacion_service import recalcular_segmentos_tienda
from apps.finanzas.models import TipoCambio
from apps.tiendas.management.sintetico import persistencia, reporte
from apps.tiendas.management.sintetico.simulacion import ZONA, Calendario, simular
from apps.usuarios.models import Usuario


def corte_de_la_simulacion(hasta):
    """Hoy se corta a la hora en punto; un día pasado se cierra a las 23:59:59."""
    hoy = timezone.localdate()
    if hasta == hoy:
        return timezone.localtime().replace(minute=0, second=0, microsecond=0)
    return datetime.combine(hasta, datetime.max.time().replace(microsecond=0), tzinfo=ZONA)


class Command(BaseCommand):
    help = 'Siembra 12 meses de datos sintéticos (catálogo, clientes, pedidos, reseñas, eventos, gastos) para una empresa.'

    def add_arguments(self, parser):
        parser.add_argument('--empresa', required=True, help='Correo de un usuario con rol empresa.')
        parser.add_argument('--meses', type=int, default=12,
                            help='Meses completos anteriores al mes en curso; se suma el mes en curso hasta la fecha de corte.')
        parser.add_argument('--clientes', type=int, default=1200)
        parser.add_argument('--pedidos', type=int, default=3000)
        parser.add_argument('--semilla', type=int, default=42)
        parser.add_argument('--hasta', type=date.fromisoformat, default=None,
                            help='Fecha de corte AAAA-MM-DD (por defecto hoy).')
        parser.add_argument('--revertir', action='store_true',
                            help='Borra la tienda dedicada y los clientes sintéticos de la empresa.')
        parser.add_argument('--reporte', help='Ruta del reporte Markdown con conteos y consultas SQL.')

    def handle(self, *args, **opciones):
        empresa = self.obtener_empresa(opciones['empresa'])
        if opciones['revertir']:
            return self.revertir(empresa)
        if min(opciones['meses'], opciones['clientes'], opciones['pedidos']) < 1:
            raise CommandError('--meses, --clientes y --pedidos deben ser positivos.')
        if persistencia.tienda_sintetica(empresa) or persistencia.clientes_sinteticos(empresa).exists():
            raise CommandError('Esa empresa ya tiene datos sintéticos. Ejecuta primero con --revertir.')
        self.sembrar(empresa, opciones)

    def obtener_empresa(self, correo):
        empresa = Usuario.objects.filter(email__iexact=correo, rol__nombre='empresa').first()
        if empresa is None:
            raise CommandError(f'No existe un usuario con rol empresa y correo {correo}.')
        return empresa

    def revertir(self, empresa):
        borrados = persistencia.revertir(empresa)
        if not borrados:
            self.stdout.write('No había datos sintéticos de esa empresa.')
            return
        self.stdout.write(self.style.SUCCESS('Datos sintéticos eliminados:'))
        for modelo, cantidad in sorted(borrados.items()):
            self.stdout.write(f'  {modelo}: {cantidad}')

    def sembrar(self, empresa, opciones):
        inicio = time.monotonic()
        hasta = opciones['hasta'] or timezone.localdate()
        calendario = Calendario(hasta, opciones['meses'], corte_de_la_simulacion(hasta))
        tipos_cambio = {c.fecha: c.usd_bob for c in TipoCambio.objects.filter(
            fecha__range=(calendario.inicio, calendario.hasta))}

        self.avance('Simulando la historia en memoria', inicio)
        simulacion = simular(random.Random(opciones['semilla']), calendario, empresa.id,
                             opciones['clientes'], opciones['pedidos'], tipos_cambio)
        self.stdout.write(f'  {len(simulacion.pedidos)} pedidos, {len(simulacion.clientes)} clientes, '
                          f'{len(simulacion.eventos)} eventos, {len(simulacion.resenas)} reseñas')

        with transaction.atomic(), persistencia.fechas_explicitas(*persistencia.MODELOS_CON_FECHA):
            self.avance('Creando tienda, clientes y catálogo', inicio)
            tienda = persistencia.crear_tienda(empresa, calendario)
            persistencia.crear_clientes(simulacion, tienda)
            persistencia.crear_catalogo(simulacion, tienda, empresa)
            persistencia.crear_cupones(simulacion, tienda)
            self.avance('Creando carritos, pedidos, pagos y envíos (corren los triggers de la base)', inicio)
            campana = persistencia.crear_carritos(simulacion, tienda)
            persistencia.crear_pedidos(simulacion, tienda)
            persistencia.crear_recuperaciones(simulacion, campana)
            persistencia.crear_pagos_y_envios(simulacion, tienda)
            self.avance('Creando reseñas, eventos y gastos', inicio)
            persistencia.crear_resenas(simulacion, tienda)
            persistencia.crear_eventos(simulacion, tienda)
            persistencia.crear_gastos(simulacion, tienda, empresa)
            self.avance('Calculando segmentos de clientes', inicio)
            recalcular_segmentos_tienda(tienda)

        texto = reporte.construir(tienda, empresa, {**opciones, 'hasta': hasta}, time.monotonic() - inicio)
        self.stdout.write(texto)
        if opciones['reporte']:
            with open(opciones['reporte'], 'w', encoding='utf-8') as archivo:
                archivo.write(texto)
            self.stdout.write(self.style.SUCCESS(f'Reporte guardado en {opciones["reporte"]}'))

    def avance(self, mensaje, inicio):
        self.stdout.write(f'[{time.monotonic() - inicio:6.1f} s] {mensaje}')
