"""
Management Command: python manage.py db_restore
Restaura un respaldo de base de datos (.sql.gz o .sql) con salvaguardas de seguridad,
desactivación temporal de triggers de negocio y resincronización de secuencias.
"""

import sys
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from apps.usuarios.services.backup_service import BackupService, BinaryDetector, DatabaseCredentials


class Command(BaseCommand):
    help = 'Restaura la base de datos desde un archivo de respaldo con salvaguarda de triggers y secuencias.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default=None,
            help='Nombre o ruta del archivo de respaldo a restaurar (ej: backup_kantu_20261005_120000.sql.gz).',
        )
        parser.add_argument(
            '--latest',
            action='store_true',
            help='Selecciona y restaura automáticamente el respaldo más reciente disponible.',
        )
        parser.add_argument(
            '--list',
            action='store_true',
            help='Lista todos los respaldos locales disponibles y finaliza.',
        )
        parser.add_argument(
            '--engine',
            type=str,
            choices=['auto', 'native', 'python'],
            default='auto',
            help="Motor de restauración: 'auto' (detecta psql o usa python), 'native' (psql) o 'python' (autónomo).",
        )
        parser.add_argument(
            '-y', '--yes',
            action='store_true',
            help='Confirma automáticamente la operación omitiendo el aviso interactivo en consola.',
        )

    def handle(self, *args, **options):
        # 1. Modo listado de respaldos
        if options['list']:
            self._list_backups()
            return

        creds = DatabaseCredentials.from_settings()
        backup_dir = BackupService.get_backup_dir()

        target_filepath = None

        if options['latest']:
            backups = BackupService.list_backups(backup_dir)
            if not backups:
                raise CommandError(f"No se encontraron respaldos en el directorio {backup_dir}.")
            target_filepath = Path(backups[0]['filepath'])
            self.stdout.write(f"Seleccionado respaldo más reciente: {self.style.WARNING(target_filepath.name)}")

        elif options['file']:
            candidate = Path(options['file'])
            if candidate.is_file():
                target_filepath = candidate.resolve()
            else:
                candidate_in_dir = backup_dir / options['file']
                if candidate_in_dir.is_file():
                    target_filepath = candidate_in_dir.resolve()
                else:
                    raise CommandError(f"No se encontró el archivo de respaldo: {options['file']}")
        else:
            self.stderr.write(self.style.ERROR("Debe especificar --file=<nombre> o --latest. Use --list para ver disponibles."))
            self._list_backups()
            raise CommandError("Parámetro de respaldo requerido.")

        # 2. Información del objetivo y advertencia de seguridad
        file_size_human = BackupService._format_bytes(target_filepath.stat().st_size)
        psql_bin = BinaryDetector.find_binary('psql')

        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Kantu Market: Protocolo de Restauración de Base de Datos ==='))
        self.stdout.write(f"Archivo Origen: {self.style.WARNING(target_filepath.name)}")
        self.stdout.write(f"Tamaño:         {file_size_human}")
        self.stdout.write(f"Base de Datos:  {self.style.ERROR(creds.name)} (Host: {creds.host})")
        self.stdout.write(f"Motor:          {options['engine']} (psql: {psql_bin or 'No disponible, usando fallback Python'})")
        self.stdout.write('')

        self.stdout.write(self.style.NOTICE('SALVAGUARDAS INTEGRADAS:'))
        self.stdout.write(' [1] Desactivación temporal de triggers de usuario (trg_actualizar_stock_item_pedido, etc.)')
        self.stdout.write(' [2] Carga ordenada de datos evitando violaciones de Foreign Key')
        self.stdout.write(' [3] Resincronización matemática de secuencias (setval)')
        self.stdout.write(' [4] Reactivación estricta de triggers y registro en LogAuditoria')
        self.stdout.write('')

        # 3. Confirmación interactiva si no se especificó --yes
        if not options['yes']:
            self.stdout.write(self.style.ERROR('ADVERTENCIA: Esta operación reemplazará los datos actuales de la base de datos.'))
            confirm = input('¿Está absolutamente seguro de que desea continuar? [s/N]: ').strip().lower()
            if confirm not in ['s', 'si', 'y', 'yes']:
                self.stdout.write(self.style.NOTICE('Operación cancelada por el usuario. No se modificó ningún dato.'))
                return

        # 4. Ejecución del protocolo de restauración
        self.stdout.write('\nRestaurando base de datos...')

        try:
            result = BackupService.restore_backup(
                filepath=str(target_filepath),
                engine=options['engine'],
            )
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"\n[ERROR CRÍTICO] Falló la restauración: {e}"))
            raise CommandError(str(e))

        self.stdout.write(self.style.SUCCESS('\n[OK] Restauración completada exitosamente.'))
        self.stdout.write(f"Archivo:   {result['filename']}")
        self.stdout.write(f"Motor:     {result['engine']}")
        self.stdout.write(f"Duración:  {result['duration_seconds']} segundos")
        self.stdout.write(self.style.SUCCESS('La base de datos se encuentra sincronizada y los triggers han sido reactivados.'))

    def _list_backups(self):
        """Muestra los respaldos disponibles en la terminal."""
        backup_dir = BackupService.get_backup_dir()
        backups = BackupService.list_backups(backup_dir)

        self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== Respaldos Disponibles en {backup_dir} ==="))
        if not backups:
            self.stdout.write(self.style.NOTICE('No hay copias de seguridad registradas.'))
            return

        self.stdout.write(f"{'Archivo':<42} {'Tamaño':<10} {'Fecha de Creación':<25} {'Tag':<15}")
        self.stdout.write('-' * 95)
        for b in backups:
            tag_str = b['tag'] if b['tag'] else '-'
            self.stdout.write(f"{b['filename']:<42} {b['size_human']:<10} {b['created_at']:<25} {tag_str:<15}")
        self.stdout.write('')
