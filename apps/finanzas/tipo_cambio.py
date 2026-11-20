"""
Tipo de cambio oficial del BCB, consultado a factura.bo (API pública, sin clave).

El dólar oficial ya no es fijo: factura.bo publica la cotización vigente cada
día a las 04:05 UTC. Se guarda una fila de `TipoCambio` por fecha y el resto del
sistema (Stripe, la tienda en USD) lee la última guardada, así que una caída de
la API externa nunca bloquea una compra.
"""

import json
import logging
import urllib.error
import urllib.request
from datetime import date
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from .models import TipoCambio

logger = logging.getLogger(__name__)

URL_HISTORIAL = 'https://api.factura.bo/ExchangeRate/history'
TIMEOUT_SEGUNDOS = 10
LIMITE_HISTORIAL = 365
# Cuántos días se piden en la actualización diaria: si un día falló, el
# siguiente cron recupera los faltantes.
DIAS_ACTUALIZACION = 7
FUENTE_POR_DEFECTO = 'Banco Central de Bolivia'


class RespuestaInvalida(ValueError):
    pass


def _decimal_positivo(valor, decimales):
    try:
        numero = Decimal(str(valor))
    except InvalidOperation:
        raise RespuestaInvalida(f'Valor no numérico: {valor!r}')
    if not numero.is_finite() or numero <= 0:
        raise RespuestaInvalida(f'Valor no positivo: {valor!r}')
    return numero.quantize(Decimal(1).scaleb(-decimales))


def _parsear_cotizacion(item):
    if not isinstance(item, dict):
        raise RespuestaInvalida('Cotización con formato inesperado.')
    try:
        fecha = date.fromisoformat(item['fecha'])
    except (KeyError, TypeError, ValueError):
        raise RespuestaInvalida(f'Fecha inválida: {item.get("fecha")!r}')
    ufv = item.get('ufv_bob')
    return {
        'fecha': fecha,
        'usd_bob': _decimal_positivo(item.get('usd_bob'), 4),
        'ufv_bob': _decimal_positivo(ufv, 5) if ufv is not None else None,
        'fuente': str(item.get('fuente') or FUENTE_POR_DEFECTO)[:100],
    }


def parsear_historial(payload):
    """Valida el sobre `{"ok", "datos": [...]}` de factura.bo y devuelve las cotizaciones válidas.

    Una cotización mala se descarta (queda en el log) sin perder las demás; un
    sobre mal formado o sin ninguna cotización válida sí es error.
    """
    if not isinstance(payload, dict) or payload.get('ok') is not True:
        raise RespuestaInvalida('La API respondió ok distinto de true.')
    datos = payload.get('datos')
    if not isinstance(datos, list):
        raise RespuestaInvalida('El historial no es una lista.')

    cotizaciones = []
    for item in datos:
        try:
            cotizaciones.append(_parsear_cotizacion(item))
        except RespuestaInvalida as exc:
            logger.warning('Cotización descartada de factura.bo: %s', exc)
    if not cotizaciones:
        raise RespuestaInvalida('El historial no trae ninguna cotización válida.')
    return cotizaciones


def _consultar_historial(cantidad):
    solicitud = urllib.request.Request(
        f'{URL_HISTORIAL}?limit={cantidad}',
        headers={'Accept': 'application/json'},
    )
    with urllib.request.urlopen(solicitud, timeout=TIMEOUT_SEGUNDOS) as respuesta:
        return json.load(respuesta)


def actualizar_tipo_cambio(cantidad=DIAS_ACTUALIZACION):
    """Trae las últimas `cantidad` cotizaciones y las guarda por fecha (idempotente).

    Devuelve cuántas cotizaciones quedaron guardadas, o None si la API falló: en
    ese caso se registra el error y se sigue usando la última cotización guardada.
    """
    try:
        cotizaciones = parsear_historial(_consultar_historial(cantidad))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.error('No se pudo actualizar el tipo de cambio desde factura.bo: %s', exc)
        return None

    for cotizacion in cotizaciones:
        fecha = cotizacion.pop('fecha')
        TipoCambio.objects.update_or_create(fecha=fecha, defaults=cotizacion)
    return len(cotizaciones)


def tipo_cambio_vigente():
    """Última cotización con fecha <= hoy en La Paz, o None si no hay ninguna guardada."""
    return TipoCambio.objects.filter(fecha__lte=timezone.localdate()).first()
