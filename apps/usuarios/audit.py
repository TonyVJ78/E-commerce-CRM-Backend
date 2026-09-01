"""
Utilidades de auditoría (CU07 — Bitácora).

`registrar_auditoria` escribe una fila en `log_auditoria`. `AuditoriaCreateMixin`
lo engancha automáticamente a las vistas genéricas de DRF que crean registros;
es el patrón a seguir al añadir nuevos endpoints de escritura.
"""

import json

from .models import LogAuditoria

ACCION_CREAR = 'CREAR'
ACCION_ACTUALIZAR = 'ACTUALIZAR'
ACCION_ELIMINAR = 'ELIMINAR'
ACCION_CERRAR_SESION = 'CERRAR_SESION'


def _json_safe(data):
    """Convierte `data` a algo serializable a JSON (o None si no se puede)."""
    if data is None:
        return None
    try:
        return json.loads(json.dumps(data, default=str))
    except (TypeError, ValueError):
        return None


def registrar_auditoria(request, accion, *, tabla, registro_id,
                        datos_anteriores=None, datos_nuevos=None):
    """Registra una acción en `log_auditoria`.

    El usuario se toma de `request.user`; si es anónimo se guarda como NULL.
    Nunca lanza excepción: un fallo de auditoría no debe tumbar la petición.
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
            datos_anteriores=_json_safe(datos_anteriores),
            datos_nuevos=_json_safe(datos_nuevos),
        )
    except Exception:  # pragma: no cover - la auditoría no debe romper el flujo
        pass


class AuditoriaCreateMixin:
    """Mixin para vistas genéricas de DRF: audita cada creación en `log_auditoria`.

    - `audit_tabla`: nombre de la tabla a registrar (por defecto, el `db_table`
      del modelo del objeto creado).
    - `get_auditoria_extra_save_kwargs()`: kwargs extra para `serializer.save()`
      (por ejemplo, inyectar el propietario).
    """

    audit_tabla = None

    def get_auditoria_extra_save_kwargs(self):
        return {}

    def perform_create(self, serializer):
        instance = serializer.save(**self.get_auditoria_extra_save_kwargs())
        registrar_auditoria(
            self.request,
            ACCION_CREAR,
            tabla=self.audit_tabla or instance._meta.db_table,
            registro_id=instance.pk,
            datos_nuevos=serializer.data,
        )
