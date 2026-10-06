"""
Management Command: python manage.py db_backup
Genera un respaldo íntegro y comprimido (.sql.gz) de la base de datos PostgreSQL (Neon Tech).
"""

from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from apps.usuarios.services.backup_service import BackupService, BinaryDetector, DatabaseCredentials


class Command(BaseCommand):
    help = 'Genera un respaldo de la base de datos en formato comprimido (.sql.gz) con política de retención.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--engine',
            type=str,
            choices=['auto', 'native', 'python'],
            default='auto',
            help="Motor a emplear: 'auto' (detecta pg_dump o usa python), 'native' (pg_dump), o 'python' (fallback autónomo).",
        )
        parser.add_argument(
            '--keep',
            type=int,
            default=7,
            help='Número de copias a retener según política FIFO (por defecto 7).',
        )
        parser.add_argument(
            '--output-dir',
            type=str,
            default=None,
            help='Directorio alternativo para guardar el respaldo (por defecto server/backups/).',
        )
        parser.add_argument(
            '--tag',
            type=str,
            default='',
            help='Etiqueta o sufijo descriptivo (ej: pre-deploy, sprint4).',
        )
        parser.add_argument(
            '--no-rotate',
            action='store_true',
            help='Desactiva la eliminación de respaldos antiguos.',
        )

    def handle(self, *args, **options):
        engine = options['engine']
        keep = 0 if options['no_rotate'] else options['keep']
        output_dir = options['output_dir']
        tag = options['tag']

        creds = DatabaseCredentials.from_settings()

        self.stdout.write(self.style.MIGRATE_HEADING('=== Kantu Market: Generador de Respaldo de Base de Datos ==='))
        self.stdout.write(f"Base de Datos: {self.style.WARNING(creds.name)}")
        self.stdout.write(f"Host:          {creds.host}:{creds.port}")
        self.stdout.write(f"Usuario:       {creds.user}")
        self.stdout.write(f"SSL Mode:      {creds.sslmode}")
        if creds.endpoint_id:
            self.stdout.write(f"Neon Endpoint: {creds.endpoint_id}")

        pg_dump_bin = BinaryDetector.find_binary('pg_dump')
        self.stdout.write(f"pg_dump:       {pg_dump_bin or 'No disponible (usando motor autónomo Python)'}")
        self.stdout.write(f"Modo Motor:    {engine}")
        self.stdout.write(f"Retención:     {keep if keep > 0 else 'Sin rotación'} copias")
        self.stdout.write('')

        self.stdout.write('Generando copia de seguridad...')

        try:
            result = BackupService.create_backup(
                output_dir=output_dir,
                engine=engine,
                keep=keep,
                tag=tag,
            )
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"\n[ERROR] Falló la generación del respaldo: {e}"))
            raise CommandError(str(e))

        self.stdout.write(self.style.SUCCESS('\n[OK] Respaldo generado exitosamente.'))
        self.stdout.write(f"Archivo:    {self.style.SUCCESS(result['filename'])}")
        self.stdout.write(f"Ubicación:  {result['filepath']}")
        self.stdout.write(f"Tamaño:     {result['filesize_human']} ({result['filesize']} bytes)")
        self.stdout.write(f"Motor:      {result['engine']}")
        self.stdout.write(f"Tablas:     {result['tables_count']}")
        self.stdout.write(f"Registros:  {result['rows_count']}")
        self.stdout.write(f"Duración:   {result['duration_seconds']} segundos")

        if result['deleted_files']:
            self.stdout.write(self.style.NOTICE('\nArchivos antiguos rotados (política FIFO):'))
            for deleted in result['deleted_files']:
                self.stdout.write(f" - {deleted}")
