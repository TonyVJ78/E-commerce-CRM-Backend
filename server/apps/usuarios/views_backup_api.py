"""
Controlador REST API para la gestion de Copias de Seguridad (CU-28).
Proporciona endpoints administrativos para visualizacion, generacion bajo demanda,
descarga segura y programacion de respaldos en PostgreSQL / Neon Tech.
"""

import datetime
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.db import connection
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.usuarios.models import LogAuditoria
from apps.usuarios.services.backup_service import (
    BackupService,
    BinaryDetector,
    DatabaseCredentials,
)

logger = logging.getLogger(__name__)

# Expresion regular estricta para mitigar vulnerabilidades de Path Traversal
FILENAME_SAFE_REGEX = re.compile(r'^[a-zA-Z0-9_\-\.]+\.sql\.gz$')

CONFIG_FILENAME = 'backup_schedule_config.json'


class IsAdminOrSuperuser(permissions.BasePermission):
    """
    Permiso estricto: requiere autenticacion valida y ser superusuario
    o poseer el rol 'administrador' (case insensitive).
    """
    message = "Acceso restringido exclusivamente a administradores del sistema."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, 'is_superuser', False):
            return True
        rol = getattr(user, 'rol', None)
        if rol and getattr(rol, 'nombre', '').strip().lower() == 'administrador':
            return True
        return False


def _get_schedule_config_path() -> Path:
    """Retorna la ruta al archivo de persistencia de configuracion de automatizacion."""
    backup_dir = BackupService.get_backup_dir()
    return backup_dir / CONFIG_FILENAME


def _calcular_proxima_ejecucion(activo: bool, frecuencia: str, hora_ejecucion: str) -> Optional[str]:
    """
    Calcula la fecha y hora UTC de la siguiente ejecucion programada
    en base a la frecuencia y hora especificada.
    """
    if not activo:
        return None

    try:
        partes = hora_ejecucion.split(':')
        hora = int(partes[0])
        minuto = int(partes[1])
    except (ValueError, IndexError):
        hora, minuto = 3, 0

    ahora = timezone.now()
    candidato = ahora.replace(hour=hora, minute=minuto, second=0, microsecond=0)

    frecuencia_norm = frecuencia.strip().lower()
    if frecuencia_norm in ('semanal', 'weekly'):
        # Si la hora de hoy ya paso, sumar dias hasta la proxima semana
        dias_a_sumar = (7 - ahora.weekday()) if ahora.weekday() != 0 or candidato <= ahora else 0
        if dias_a_sumar == 0 and candidato <= ahora:
            dias_a_sumar = 7
        proxima = candidato + datetime.timedelta(days=dias_a_sumar)
    else:
        # Frecuencia diaria
        if candidato <= ahora:
            proxima = candidato + datetime.timedelta(days=1)
        else:
            proxima = candidato

    return proxima.isoformat()


def _leer_config_automatizacion() -> Dict[str, Any]:
    """Carga la configuracion de automatizacion guardada o retorna valores por defecto."""
    config_path = _get_schedule_config_path()
    defaults = {
        "activo": True,
        "frecuencia": "diaria",
        "hora_ejecucion": "03:00",
        "retencion_dias": 30,
    }

    if config_path.is_file():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                defaults.update(saved)
        except Exception as e:
            logger.warning("Error al leer configuracion de automatizacion de backups: %s", e)

    defaults["proxima_ejecucion"] = _calcular_proxima_ejecucion(
        defaults.get("activo", True),
        defaults.get("frecuencia", "diaria"),
        defaults.get("hora_ejecucion", "03:00"),
    )
    return defaults


def _guardar_config_automatizacion(data: Dict[str, Any]) -> Dict[str, Any]:
    """Persiste la configuracion de automatizacion en disco."""
    config_path = _get_schedule_config_path()
    payload = {
        "activo": bool(data.get("activo", True)),
        "frecuencia": "semanal" if str(data.get("frecuencia", "")).lower() == "semanal" else "diaria",
        "hora_ejecucion": str(data.get("hora_ejecucion", "03:00")).strip(),
        "retencion_dias": max(1, int(data.get("retencion_dias", 30))),
    }

    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        logger.error("No se pudo escribir archivo de configuracion de backups: %s", e)
        raise RuntimeError(f"Error al persistir configuracion: {e}")

    payload["proxima_ejecucion"] = _calcular_proxima_ejecucion(
        payload["activo"],
        payload["frecuencia"],
        payload["hora_ejecucion"],
    )
    return payload


def _contar_tablas_publicas() -> int:
    """Obtiene el numero de tablas publicas registradas en la base de datos."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
            """)
            row = cursor.fetchone()
            if row and row[0]:
                return int(row[0])
    except Exception as e:
        logger.debug("No se pudo consultar conteo de tablas publicas: %s", e)
    return 38


class BackupListApiView(APIView):
    """
    GET /api/admin/backups/
    Lista los archivos de respaldo disponibles en el servidor con metadatos estructurados.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request: HttpRequest) -> Response:
        backup_dir = BackupService.get_backup_dir()
        archivos = BackupService.list_backups(backup_dir)

        # Buscar conteo historico en logs de auditoria si esta disponible
        tablas_defecto = _contar_tablas_publicas()
        logs_backup = {
            log.datos_nuevos.get('archivo'): log.datos_nuevos
            for log in LogAuditoria.objects.filter(accion='BACKUP').order_by('-fecha')[:100]
            if isinstance(log.datos_nuevos, dict) and 'archivo' in log.datos_nuevos
        }

        backups_list: List[Dict[str, Any]] = []
        total_bytes = 0

        for item in archivos:
            nombre = item['filename']
            stat_bytes = item['size_bytes']
            total_bytes += stat_bytes

            log_detalles = logs_backup.get(nombre, {})
            tablas_inc = log_detalles.get('tablas') or tablas_defecto

            tipo = "automatico" if ("auto" in nombre.lower() or "cron" in nombre.lower()) else "manual"

            backups_list.append({
                "id": nombre,
                "nombre": nombre,
                "tamano_bytes": stat_bytes,
                "tamano_formateado": item['size_human'],
                "fecha_creacion": item['created_at'],
                "tipo": tipo,
                "tablas_incluidas": tablas_inc,
            })

        # Ordenar de mas reciente a mas antiguo
        backups_list.sort(key=lambda x: x["fecha_creacion"], reverse=True)

        total_mb = round(total_bytes / (1024 * 1024), 2)
        ultimo_respaldo = backups_list[0]["fecha_creacion"] if backups_list else None

        resumen = {
            "total_archivos": len(backups_list),
            "espacio_total_mb": total_mb,
            "ultimo_respaldo": ultimo_respaldo,
        }

        return Response({
            "backups": backups_list,
            "resumen": resumen,
        }, status=status.HTTP_200_OK)


class BackupGenerarApiView(APIView):
    """
    POST /api/admin/backups/generar/
    Genera un respaldo atomico completo comprimido con gzip de la base de datos PostgreSQL.
    Registra la operacion en LogAuditoria (CU-23).
    """
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request: HttpRequest) -> Response:
        tag = request.data.get('tag', '').strip() if isinstance(request.data, dict) else ''
        backup_dir = BackupService.get_backup_dir()
        config_auto = _leer_config_automatizacion()
        retencion_keep = config_auto.get("retencion_dias", 30)

        try:
            resultado = BackupService.create_backup(
                output_dir=str(backup_dir),
                engine='auto',
                keep=retencion_keep,
                tag=tag,
                user=request.user,
            )

            # Registro explicito complementario para la bitacora forense de auditoria
            ip_cliente = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
            if ',' in ip_cliente:
                ip_cliente = ip_cliente.split(',')[0].strip()

            LogAuditoria.objects.create(
                usuario=request.user,
                tabla_afectada='database',
                registro_id=0,
                accion='GENERAR_BACKUP',
                datos_anteriores=None,
                datos_nuevos={
                    'archivo': resultado['filename'],
                    'tamano_bytes': resultado['filesize'],
                    'tamano_humano': resultado['filesize_human'],
                    'motor': resultado['engine'],
                    'duracion_segundos': resultado['duration_seconds'],
                    'tablas_incluidas': resultado['tables_count'],
                    'ip': ip_cliente,
                    'fecha_generacion': resultado['timestamp'],
                },
            )

            backup_dto = {
                "id": resultado['filename'],
                "nombre": resultado['filename'],
                "tamano_bytes": resultado['filesize'],
                "tamano_formateado": resultado['filesize_human'],
                "fecha_creacion": resultado['timestamp'],
                "tipo": "manual",
                "tablas_incluidas": resultado['tables_count'] or _contar_tablas_publicas(),
            }

            return Response({
                "success": True,
                "mensaje": f"Copia de seguridad generada con exito: {resultado['filename']}",
                "backup": backup_dto,
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.exception("Fallo al generar respaldo via API: %s", e)
            return Response({
                "success": False,
                "mensaje": f"Error al generar la copia de seguridad: {str(e)}",
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BackupDescargarApiView(APIView):
    """
    GET /api/admin/backups/descargar/?archivo=<nombre_archivo>
    Descarga segura de archivo de respaldo validando la prevencion de Path Traversal.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request: HttpRequest) -> HttpResponse:
        nombre_archivo = request.query_params.get('archivo') or request.GET.get('archivo')
        if not nombre_archivo:
            return Response(
                {"detail": "Debe especificar el parametro 'archivo'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        nombre_archivo = nombre_archivo.strip()

        # 1. Validacion de patron de nombre seguro
        if not FILENAME_SAFE_REGEX.match(nombre_archivo):
            logger.warning("Intento de descarga de archivo no permitido: %r", nombre_archivo)
            return Response(
                {"detail": "Nombre de archivo invalido o con formato no permitido."},
                status=status.HTTP_400_BAD_REQUEST
            )

        backup_dir = BackupService.get_backup_dir()
        filepath = (backup_dir / nombre_archivo).resolve()

        # 2. Prevencion de Path Traversal asegurando que este contenido en backup_dir
        try:
            if not filepath.is_relative_to(backup_dir) or not filepath.is_file():
                return Response(
                    {"detail": "El archivo de respaldo no existe en el almacenamiento seguro."},
                    status=status.HTTP_404_NOT_FOUND
                )
        except AttributeError:
            if not str(filepath).startswith(str(backup_dir)) or not filepath.is_file():
                return Response(
                    {"detail": "El archivo de respaldo no existe en el almacenamiento seguro."},
                    status=status.HTTP_404_NOT_FOUND
                )

        filesize = filepath.stat().st_size

        # 3. Registro en auditoria forense
        try:
            ip_cliente = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
            if ',' in ip_cliente:
                ip_cliente = ip_cliente.split(',')[0].strip()

            LogAuditoria.objects.create(
                usuario=request.user,
                tabla_afectada='database',
                registro_id=0,
                accion='DESCARGA_BACKUP',
                datos_anteriores=None,
                datos_nuevos={
                    'archivo': nombre_archivo,
                    'tamano_bytes': filesize,
                    'tamano_humano': BackupService._format_bytes(filesize),
                    'ip': ip_cliente,
                    'fecha_descarga': timezone.now().isoformat(),
                },
            )
        except Exception as e:
            logger.warning("No se pudo auditar descarga de backup: %s", e)

        # 4. Retornar archivo en streaming con cabeceras de descarga
        response = FileResponse(
            open(filepath, 'rb'),
            as_attachment=True,
            filename=nombre_archivo,
            content_type='application/gzip',
        )
        response['Content-Length'] = filesize
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate, private'
        response['Pragma'] = 'no-cache'
        return response


class BackupAutomatizacionApiView(APIView):
    """
    GET /api/admin/backups/automatizacion/
    POST /api/admin/backups/automatizacion/
    Consulta y actualiza la configuracion de programacion automatica y retencion de respaldos.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request: HttpRequest) -> Response:
        config_data = _leer_config_automatizacion()
        return Response(config_data, status=status.HTTP_200_OK)

    def post(self, request: HttpRequest) -> Response:
        data = request.data if isinstance(request.data, dict) else {}

        # Validaciones de parametros
        hora = str(data.get('hora_ejecucion', '03:00')).strip()
        if not re.match(r'^(?:[01]\d|2[0-3]):[0-5]\d$', hora):
            return Response(
                {"detail": "Formato de hora invalido. Use el formato HH:MM (ej. 03:00)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            retencion = int(data.get('retencion_dias', 30))
            if retencion < 1 or retencion > 365:
                raise ValueError()
        except (ValueError, TypeError):
            return Response(
                {"detail": "Los dias de retencion deben ser un numero entre 1 y 365."},
                status=status.HTTP_400_BAD_REQUEST
            )

        frecuencia = str(data.get('frecuencia', 'diaria')).strip().lower()
        if frecuencia not in ('diaria', 'diario', 'semanal', 'weekly'):
            return Response(
                {"detail": "Frecuencia invalida. Debe ser 'diaria' o 'semanal'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            config_actualizada = _guardar_config_automatizacion(data)

            # Registrar en LogAuditoria
            LogAuditoria.objects.create(
                usuario=request.user,
                tabla_afectada='backup_automatizacion',
                registro_id=0,
                accion='CONFIG_AUTOMATIZACION',
                datos_anteriores=None,
                datos_nuevos=config_actualizada,
            )

            return Response({
                "success": True,
                "mensaje": "Configuracion de automatizacion guardada exitosamente.",
                "config": config_actualizada,
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception("Error al guardar configuracion de backups: %s", e)
            return Response(
                {"detail": f"Error interno al guardar la configuracion: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# Alias unificado BackupApiController para satisfacer la denominacion requerida
class BackupApiController:
    list_view = BackupListApiView.as_view()
    generar_view = BackupGenerarApiView.as_view()
    descargar_view = BackupDescargarApiView.as_view()
    automatizacion_view = BackupAutomatizacionApiView.as_view()
