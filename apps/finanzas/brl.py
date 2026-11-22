"""BRL indicativo: ninguna actualización de precios, pedidos ni cobros.

Requiere habilitación y política explícitas. En demo acepta solo fixtures DEMO.
La descarga real exige aprobación independiente del proveedor.
"""
import json
import logging
import urllib.error
import urllib.request
from datetime import date
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.usuarios.audit import registrar_auditoria, snapshot_instancia, ACCION_ACTUALIZAR
from .conversion import convertir_importe
from .models import TipoCambio

logger = logging.getLogger(__name__)
URL_BRL = 'https://api.frankfurter.dev/v2/providers/bcbo/rate/brl/bob'
MAX_BYTES = 16384


def brl_habilitado():
    return bool(getattr(settings, 'CU39_BRL_ENABLED', False) and (
        getattr(settings, 'CU39_BRL_DEMO', False) or getattr(settings, 'CU39_BRL_PROVIDER_APPROVED', False)))


def politica_brl():
    dias = getattr(settings, 'CU39_BRL_MAX_AGE_DAYS', None)
    return dias if type(dias) is int and 0 <= dias <= 366 else None


def estado_brl():
    estado = {'estado': 'deshabilitada', 'disponible': False, 'fecha': None,
              'tasa_bob_por_brl': None, 'fuente': None, 'demo': bool(getattr(settings, 'CU39_BRL_DEMO', False))}
    if not brl_habilitado():
        return estado
    if politica_brl() is None:
        return {**estado, 'estado': 'politica_pendiente'}
    cotizacion = TipoCambio.objects.filter(fecha__lte=timezone.localdate(), brl_bob__isnull=False).first()
    if cotizacion is None:
        return {**estado, 'estado': 'sin_cotizacion'}
    if (timezone.localdate() - cotizacion.fecha).days > politica_brl():
        return {**estado, 'estado': 'vencida', 'fecha': cotizacion.fecha.isoformat()}
    es_demo = (cotizacion.brl_fuente or '').upper().startswith('DEMO')
    if es_demo != estado['demo']:
        return {**estado, 'estado': 'fuente_no_permitida'}
    try:
        tasa = Decimal(str(cotizacion.brl_bob))
        if not tasa.is_finite() or not Decimal('0') < tasa < Decimal('10000000000'):
            raise ValueError('Tasa inválida.')
    except (InvalidOperation, ValueError):
        return {**estado, 'estado': 'sin_cotizacion'}
    return {**estado, 'estado': 'disponible', 'disponible': True, 'fecha': cotizacion.fecha.isoformat(),
            'tasa_bob_por_brl': str(cotizacion.brl_bob), 'fuente': cotizacion.brl_fuente}


def contexto_brl(context):
    # Una observación por solicitud, nunca una consulta por variante.
    if '_cu39_brl' not in context:
        context['_cu39_brl'] = estado_brl()
    return context['_cu39_brl']


def visualizar_brl(precio, efectivo, estado):
    if not estado['disponible']:
        return None
    try:
        return {'moneda': 'BRL', 'precio_normal': str(convertir_importe(precio, bob_por_destino=estado['tasa_bob_por_brl'])),
                'precio_efectivo': str(convertir_importe(efectivo, bob_por_destino=estado['tasa_bob_por_brl'])),
                'cotizacion_fecha': estado['fecha'], 'tasa_bob_por_brl': estado['tasa_bob_por_brl'],
                'fuente': estado['fuente'], 'demo': estado['demo']}
    except ValueError:
        return None  # Un precio no representable conserva su precio BOB.


def guardar_observacion_brl(payload, *, sintetica=False):
    if not brl_habilitado() or politica_brl() is None:
        return {'estado': 'deshabilitada'}
    if sintetica != bool(getattr(settings, 'CU39_BRL_DEMO', False)):
        raise ValueError('No se mezclan fixtures demo con cotizaciones reales.')
    if not isinstance(payload, dict) or payload.get('base') != 'BRL' or payload.get('quote') != 'BOB':
        raise ValueError('Par monetario BRL/BOB inválido.')
    try:
        fecha = date.fromisoformat(payload['date'])
        tasa = Decimal(str(payload['rate']))
        if fecha > timezone.localdate() or not tasa.is_finite() or not Decimal('0') < tasa < Decimal('10000000000'):
            raise ValueError('Fecha o tasa BRL inválida.')
        # No aceptar una cotización que ya excede la política aprobada/demo.
        if (timezone.localdate() - fecha).days > politica_brl():
            raise ValueError('La cotización BRL está vencida.')
        tasa = tasa.quantize(Decimal('0.00000001'))
        if tasa <= 0:
            raise ValueError('La tasa BRL se redondea a cero.')
    except (KeyError, TypeError, InvalidOperation) as exc:
        raise ValueError('Observación BRL mal formada.') from exc
    fuente = 'DEMO SINTÉTICA — no cotización real' if sintetica else 'Banco Central de Bolivia vía Frankfurter — indicativa'
    with transaction.atomic():
        fila = TipoCambio.objects.select_for_update().filter(fecha=fecha).first()
        if fila is None:
            logger.warning('CU39 BRL pendiente: falta fila USD para la misma fecha %s', fecha)
            return {'estado': 'sin_fila_usd', 'fecha': fecha.isoformat()}
        anterior = snapshot_instancia(fila)
        if fila.brl_bob == tasa and fila.brl_fuente == fuente:
            return {'estado': 'sin_cambios', 'fecha': fecha.isoformat()}
        fila.brl_bob, fila.brl_fuente, fila.brl_obtenido_en = tasa, fuente, timezone.now()
        fila.save(update_fields=['brl_bob', 'brl_fuente', 'brl_obtenido_en'])
        registrar_auditoria(None, ACCION_ACTUALIZAR, tabla='tipo_cambio', registro_id=fila.pk,
                           datos_anteriores=anterior, datos_nuevos=snapshot_instancia(fila))
    return {'estado': 'guardada', 'fecha': fecha.isoformat()}


def actualizar_brl():
    # La demostración no llama a Internet, incluso si la función se invoca.
    if (not brl_habilitado() or politica_brl() is None or getattr(settings, 'CU39_BRL_DEMO', False)
            or not getattr(settings, 'CU39_BRL_PROVIDER_APPROVED', False)):
        return {'estado': 'proveedor_no_autorizado'}
    try:
        solicitud = urllib.request.Request(URL_BRL, headers={'Accept': 'application/json'})
        with urllib.request.urlopen(solicitud, timeout=10) as respuesta:
            cuerpo = respuesta.read(MAX_BYTES + 1)
        if len(cuerpo) > MAX_BYTES:
            raise ValueError('Respuesta BRL demasiado grande.')
        payload = json.loads(cuerpo, parse_float=Decimal, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Número inválido')))
        return guardar_observacion_brl(payload)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        # Sin reintentos inmediatos: la siguiente ejecución explícita podrá reintentar.
        logger.warning('CU39 BRL: actualización no aplicada; se conserva observación anterior.')
        return {'estado': 'proveedor_no_disponible'}
