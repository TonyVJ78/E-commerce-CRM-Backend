"""
Vistas administrativas para el Panel de Control y Descarga de Respaldos en Django Admin.
Protegidas con verificación estricta para Superadministradores (is_superuser = True).
"""

import logging
import os
import re
from pathlib import Path

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.usuarios.models import LogAuditoria
from apps.usuarios.services.backup_service import (
    BackupService,
    BinaryDetector,
    DatabaseCredentials,
)

logger = logging.getLogger(__name__)

# Expresión regular para validar nombres de archivo seguros y prevenir Path Traversal
FILENAME_SAFE_REGEX = re.compile(r'^backup_kantu_\d{8}_\d{6}(?:_[a-zA-Z0-9_\-\.]+)?\.sql\.gz$')


def _check_superuser(request: HttpRequest) -> None:
    """Verifica autenticación y privilegios de superadministrador."""
    if not request.user.is_authenticated:
        raise PermissionDenied("Debe iniciar sesión para acceder a este recurso.")
    if not request.user.is_superuser:
        raise PermissionDenied("Acceso restringido exclusivamente a Superadministradores.")


@require_http_methods(['GET', 'POST'])
def admin_backups_dashboard_view(request: HttpRequest) -> HttpResponse:
    """
    Panel administrativo de Respaldos de Base de Datos.
    - GET: Lista los archivos de respaldo disponibles, métricas del servidor y credenciales.
    - POST: Genera un nuevo respaldo invocando BackupService.create_backup().
    """
    _check_superuser(request)
    backup_dir = BackupService.get_backup_dir()

    if request.method == 'POST':
        tag = request.POST.get('tag', '').strip()
        try:
            keep = int(request.POST.get('keep', 7))
            if keep < 1:
                keep = 7
        except (ValueError, TypeError):
            keep = 7

        try:
            result = BackupService.create_backup(
                output_dir=str(backup_dir),
                engine='auto',
                keep=keep,
                tag=tag,
                user=request.user,
            )
            messages.success(
                request,
                f"Copia de seguridad generada con éxito: {result['filename']} "
                f"({result['filesize_human']} - {result['tables_count']} tablas / {result['rows_count']} filas en {result['duration_seconds']}s)."
            )
            if result.get('deleted_files'):
                messages.info(
                    request,
                    f"Política FIFO aplicada: Se rotaron {len(result['deleted_files'])} copias antiguas."
                )
        except Exception as e:
            logger.exception("Error al generar respaldo desde Django Admin: %s", e)
            messages.error(request, f"Error al generar la copia de seguridad: {e}")

        return redirect('admin_backups_dashboard')

    # GET: Listado y contexto para la plantilla
    backups = BackupService.list_backups(backup_dir)
    creds = DatabaseCredentials.from_settings()
    pg_dump_bin = BinaryDetector.find_binary('pg_dump')

    total_bytes = sum(b['size_bytes'] for b in backups)
    total_human = BackupService._format_bytes(total_bytes) if backups else "0 B"

    context = {
        'title': 'Copias de Seguridad de Base de Datos (Disaster Recovery)',
        'backups': backups,
        'total_backups': len(backups),
        'total_storage_human': total_human,
        'creds': creds,
        'pg_dump_available': bool(pg_dump_bin),
        'pg_dump_path': pg_dump_bin,
        'backup_dir': str(backup_dir),
        'opts': {'app_label': 'usuarios', 'app_config': {'verbose_name': 'Usuarios'}},
        'has_permission': True,
        'is_nav_open': True,
    }

    return render(request, 'admin/usuarios/backups.html', context)


@require_http_methods(['GET'])
def admin_backup_download_view(request: HttpRequest, filename: str) -> HttpResponse:
    """
    Descarga segura de un archivo de respaldo específico.
    Previene Path Traversal y registra la acción en LogAuditoria.
    """
    _check_superuser(request)

    # Validar nombre del archivo contra regex seguro
    if not FILENAME_SAFE_REGEX.match(filename):
        logger.warning("Intento de descarga con nombre de archivo no permitido: %r", filename)
        raise Http404("Nombre de archivo inválido o sospechoso.")

    backup_dir = BackupService.get_backup_dir()
    filepath = (backup_dir / filename).resolve()

    # Prevenir Path Traversal asegurando que el archivo resida en backup_dir
    try:
        if not filepath.is_relative_to(backup_dir) or not filepath.is_file():
            raise Http404("El archivo de respaldo no existe.")
    except AttributeError:
        # Fallback para Python < 3.9
        if not str(filepath).startswith(str(backup_dir)) or not filepath.is_file():
            raise Http404("El archivo de respaldo no existe.")

    filesize = filepath.stat().st_size

    # Registro forense en LogAuditoria
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
                'archivo': filename,
                'tamano_bytes': filesize,
                'tamano_humano': BackupService._format_bytes(filesize),
                'ip': ip_cliente,
                'fecha_descarga': timezone.now().isoformat(),
            },
        )
    except Exception as e:
        logger.warning("No se pudo registrar la descarga en LogAuditoria: %s", e)

    response = FileResponse(
        open(filepath, 'rb'),
        as_attachment=True,
        filename=filename,
        content_type='application/gzip',
    )
    response['Content-Length'] = filesize
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate, private'
    response['Pragma'] = 'no-cache'
    return response
