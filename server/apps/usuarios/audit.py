"""
Utilidades de auditoría (CU07 — Bitácora).

`registrar_auditoria` escribe una fila en `log_auditoria`. Los mixins
(`AuditoriaCreateMixin`, `AuditoriaUpdateMixin`, `AuditoriaDeleteMixin`) lo
enganchan automáticamente a las vistas genéricas de DRF que crean, modifican o
eliminan registros; es el patrón a seguir al añadir nuevos endpoints de escritura.

Para una vista que no es genérica (un `APIView` con lógica propia) se llama a
`registrar_auditoria(request, ACCION_*, tabla=..., registro_id=...)` a mano.
"""

import json
import logging

from django.forms.models import model_to_dict

from .models import LogAuditoria

logger = logging.getLogger(__name__)

ACCION_CREAR = 'CREAR'
ACCION_ACTUALIZAR = 'ACTUALIZAR'
ACCION_ELIMINAR = 'ELIMINAR'
ACCION_CERRAR_SESION = 'CERRAR_SESION'

# Campos que nunca deben quedar registrados en texto plano en la bitácora.
CAMPOS_SENSIBLES = {'password', 'contrasena', 'contraseña', 'token', 'secret'}


def _json_safe(data):
    """Convierte `data` a algo serializable a JSON (o None si no se puede)."""
    if data is None:
        return None
    try:
        return json.loads(json.dumps(data, default=str))
    except (TypeError, ValueError):
        return None


def _redactar(data):
    """Reemplaza los valores de campos sensibles por '***' antes de auditar."""
    if not isinstance(data, dict):
        return data
    return {
        clave: ('***' if clave.lower() in CAMPOS_SENSIBLES else valor)
        for clave, valor in data.items()
    }


def snapshot_instancia(instance):
    """Devuelve un dict JSON-safe con el estado actual de una instancia de modelo.

    Se usa para capturar `datos_anteriores` justo antes de un UPDATE o DELETE.
    """
    if instance is None:
        return None
    try:
        return _json_safe(_redactar(model_to_dict(instance)))
    except Exception:
        logger.exception('No se pudo serializar la instancia %r para auditoría', instance)
        return None


def registrar_auditoria(request, accion, *, tabla, registro_id,
                        datos_anteriores=None, datos_nuevos=None):
    """Registra una acción en `log_auditoria`.

    El usuario se toma de `request.user`; si es anónimo se guarda como NULL.
    Nunca lanza excepción: un fallo de auditoría no debe tumbar la petición,
    pero sí se deja constancia en el log de la aplicación.
    """
    usuario = getattr(request, 'user', None)
    if usuario is not None and not getattr(usuario, 'is_authenticated', False):
        usuario = None

    try:
        LogAuditoria.objects.create(
            usuario=usuario,
            tabla_afectada=tabla,
            registro_id=registro_id or 0,
            accion=accion,
            datos_anteriores=_json_safe(_redactar(datos_anteriores)),
            datos_nuevos=_json_safe(_redactar(datos_nuevos)),
        )
    except Exception:
        logger.exception(
            'Fallo al registrar auditoría (accion=%s tabla=%s registro_id=%s)',
            accion, tabla, registro_id,
        )


class _AuditoriaMixinBase:
    """Config común a los mixins de auditoría.

    - `audit_tabla`: nombre de la tabla a registrar (por defecto, el `db_table`
      del modelo afectado).
    - `get_auditoria_extra_save_kwargs()`: kwargs extra para `serializer.save()`
      (por ejemplo, inyectar el propietario).
    """

    audit_tabla = None

    def get_auditoria_extra_save_kwargs(self):
        return {}

    def _audit_tabla_para(self, instance):
        return self.audit_tabla or instance._meta.db_table


class AuditoriaCreateMixin(_AuditoriaMixinBase):
    """Mixin para vistas genéricas de DRF: audita cada creación en `log_auditoria`."""

    def perform_create(self, serializer):
        instance = serializer.save(**self.get_auditoria_extra_save_kwargs())
        registrar_auditoria(
            self.request,
            ACCION_CREAR,
            tabla=self._audit_tabla_para(instance),
            registro_id=instance.pk,
            datos_nuevos=serializer.data,
        )


class AuditoriaUpdateMixin(_AuditoriaMixinBase):
    """Mixin para vistas genéricas de DRF: audita cada actualización (PUT/PATCH).

    Captura el estado previo de la instancia antes de guardar, de modo que la
    fila de `log_auditoria` conserve tanto `datos_anteriores` como `datos_nuevos`.
    """

    def perform_update(self, serializer):
        datos_anteriores = snapshot_instancia(serializer.instance)
        instance = serializer.save(**self.get_auditoria_extra_save_kwargs())
        registrar_auditoria(
            self.request,
            ACCION_ACTUALIZAR,
            tabla=self._audit_tabla_para(instance),
            registro_id=instance.pk,
            datos_anteriores=datos_anteriores,
            datos_nuevos=serializer.data,
        )


class AuditoriaDeleteMixin(_AuditoriaMixinBase):
    """Mixin para vistas genéricas de DRF: audita cada borrado (DELETE).

    Sirve tanto para el borrado físico (`instance.delete()`) como para el
    borrado lógico si la vista sobrescribe `perform_destroy` para hacer
    `instance.activo = False; instance.save()` — en ese caso conviene usar
    `AuditoriaUpdateMixin` y registrar `ACCION_ACTUALIZAR`.
    """

    def perform_destroy(self, instance):
        datos_anteriores = snapshot_instancia(instance)
        tabla = self._audit_tabla_para(instance)
        registro_id = instance.pk
        instance.delete()
        registrar_auditoria(
            self.request,
            ACCION_ELIMINAR,
            tabla=tabla,
            registro_id=registro_id,
            datos_anteriores=datos_anteriores,
        )
