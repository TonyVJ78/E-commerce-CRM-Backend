"""
Pruebas unitarias para el servicio de Respaldo y Restauración de Base de Datos (BackupService).
"""

import gzip
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.usuarios.services.backup_service import (
    BackupService,
    BinaryDetector,
    DatabaseCredentials,
)


class DatabaseCredentialsTests(TestCase):
    """Pruebas de extracción de credenciales desde settings y variables de entorno."""

    def test_credentials_from_settings(self):
        creds = DatabaseCredentials.from_settings()
        self.assertTrue(creds.name)
        self.assertTrue(creds.host)
        self.assertIn(creds.sslmode, ['require', 'prefer'])
        if 'neon.tech' in creds.host:
            self.assertTrue(creds.endpoint_id)

    def test_database_url_parsing(self):
        url = 'postgresql://usr_kantu:pwd123@ep-cool-sample-123.sa-east-1.aws.neon.tech:5432/kantu_db?sslmode=require'
        with patch.dict(os.environ, {'DATABASE_URL': url}):
            creds = DatabaseCredentials.from_settings()
            self.assertEqual(creds.name, 'kantu_db')
            self.assertEqual(creds.user, 'usr_kantu')
            self.assertEqual(creds.password, 'pwd123')
            self.assertEqual(creds.host, 'ep-cool-sample-123.sa-east-1.aws.neon.tech')
            self.assertEqual(creds.port, 5432)
            self.assertEqual(creds.sslmode, 'require')
            self.assertEqual(creds.endpoint_id, 'ep-cool-sample-123')


class BinaryDetectorTests(TestCase):
    """Pruebas para el detector de binarios nativos."""

    def test_find_binary_non_existent(self):
        res = BinaryDetector.find_binary('non_existent_binary_xyz_123')
        self.assertIsNone(res)


class FormatSqlValueTests(TestCase):
    """Pruebas de formateo seguro de tipos para PostgreSQL."""

    def test_format_null_and_bools(self):
        self.assertEqual(BackupService._format_sql_value(None), 'NULL')
        self.assertEqual(BackupService._format_sql_value(True), 'TRUE')
        self.assertEqual(BackupService._format_sql_value(False), 'FALSE')

    def test_format_numbers(self):
        self.assertEqual(BackupService._format_sql_value(100), '100')
        self.assertEqual(BackupService._format_sql_value(49.99), '49.99')

    def test_format_strings_with_quotes(self):
        self.assertEqual(BackupService._format_sql_value("Café d'Or"), "'Café d''Or'")

    def test_format_json(self):
        data = {'categoria': 'Café', 'tags': ['organico', 'grano']}
        res = BackupService._format_sql_value(data)
        self.assertTrue(res.startswith("'{"))
        self.assertTrue(res.endswith("}'"))
        self.assertIn("organico", res)

    def test_format_postgresql_array(self):
        # Array vacío
        self.assertEqual(BackupService._format_sql_value([], is_array=True), "'{}'")
        # Array con elementos
        res = BackupService._format_sql_value(['organico', 'yungas'], is_array=True)
        self.assertEqual(res, '\'{"organico","yungas"}\'')


class BackupRetentionAndCreationTests(TestCase):
    """Pruebas de generación y rotación de copias."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_rotation_fifo(self):
        temp_path = Path(self.temp_dir)
        # Crear 5 archivos ficticios con timestamps escalonados
        for i in range(5):
            fname = f"backup_kantu_2026100{i}_120000.sql.gz"
            fpath = temp_path / fname
            with gzip.open(fpath, 'wt') as gz:
                gz.write(f"-- Backup {i}")
            # Simular mtime
            mtime = 1000 + i * 100
            os.utime(fpath, (mtime, mtime))

        # Retener solo 3 copias
        deleted = BackupService.rotate_backups(temp_path, keep=3)
        self.assertEqual(len(deleted), 2)

        remaining = BackupService.list_backups(temp_path)
        self.assertEqual(len(remaining), 3)
        # Los más recientes deben ser 20261004, 20261003, 20261002
        remaining_names = [b['filename'] for b in remaining]
        self.assertIn('backup_kantu_20261004_120000.sql.gz', remaining_names)
        self.assertIn('backup_kantu_20261003_120000.sql.gz', remaining_names)
        self.assertIn('backup_kantu_20261002_120000.sql.gz', remaining_names)

    def test_create_and_read_backup(self):
        # Crear un respaldo real en carpeta temporal
        result = BackupService.create_backup(
            output_dir=self.temp_dir,
            engine='python',
            keep=5,
            tag='unit-test',
        )
        self.assertTrue(result['success'])
        self.assertTrue(os.path.isfile(result['filepath']))
        self.assertTrue(result['filesize'] > 0)
        self.assertTrue(result['tables_count'] > 0)

        # Leer archivo gzip generado y verificar secciones obligatorias
        with gzip.open(result['filepath'], 'rt', encoding='utf-8') as gz:
            content = gz.read()

        self.assertIn('Kantu Market', content)
        self.assertIn('DISABLE TRIGGER USER', content)
        self.assertIn('ENABLE TRIGGER USER', content)
        self.assertIn('TRUNCATE TABLE', content)
        self.assertIn('setval', content)


class AdminBackupViewsSecurityTests(TestCase):
    """Pruebas de control de acceso y seguridad para las vistas administrativas de backup."""

    def setUp(self):
        from apps.usuarios.models import LogAuditoria, Rol, Usuario
        self.rol_admin, _ = Rol.objects.get_or_create(nombre='Administrador')
        self.rol_cliente, _ = Rol.objects.get_or_create(nombre='Cliente')

        self.superuser = Usuario.objects.create_superuser(
            email='superadmin@kantu.bo',
            password='Password123!',
            rol=self.rol_admin,
        )
        self.regular_user = Usuario.objects.create_user(
            email='cliente@kantu.bo',
            password='Password123!',
            rol=self.rol_cliente,
        )

        self.temp_dir = tempfile.mkdtemp()
        self.test_filename = 'backup_kantu_20261005_120000_seguridad.sql.gz'
        self.test_filepath = Path(self.temp_dir) / self.test_filename
        with gzip.open(self.test_filepath, 'wt', encoding='utf-8') as gz:
            gz.write("-- Test backup content")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_anonymous_user_access_denied(self):
        from django.urls import reverse
        response = self.client.get(reverse('admin_backups_dashboard'))
        self.assertEqual(response.status_code, 403)

    def test_regular_user_access_denied(self):
        from django.urls import reverse
        self.client.force_login(self.regular_user)
        response = self.client.get(reverse('admin_backups_dashboard'))
        self.assertEqual(response.status_code, 403)

    def test_superuser_access_allowed(self):
        from django.urls import reverse
        self.client.force_login(self.superuser)
        with patch.object(BackupService, 'get_backup_dir', return_value=Path(self.temp_dir)):
            response = self.client.get(reverse('admin_backups_dashboard'))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Copias de Seguridad de Base de Datos')
            self.assertContains(response, self.test_filename)

    def test_superuser_generate_backup_post(self):
        from django.urls import reverse
        self.client.force_login(self.superuser)
        with patch.object(BackupService, 'create_backup') as mock_create:
            mock_create.return_value = {
                'success': True,
                'filename': 'backup_kantu_20261005_999999_post.sql.gz',
                'filepath': str(self.test_filepath),
                'filesize': 1024,
                'filesize_human': '1.0 KB',
                'tables_count': 45,
                'rows_count': 2000,
                'duration_seconds': 1.5,
                'deleted_files': [],
            }
            response = self.client.post(
                reverse('admin_backups_dashboard'),
                {'tag': 'demo-post', 'keep': '7'},
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, reverse('admin_backups_dashboard'))
            mock_create.assert_called_once()

    def test_download_backup_anonymous_and_regular_denied(self):
        from django.urls import reverse
        # Usuario anónimo
        response = self.client.get(reverse('admin_backup_download', kwargs={'filename': self.test_filename}))
        self.assertEqual(response.status_code, 403)

        # Usuario no superadmin
        self.client.force_login(self.regular_user)
        response = self.client.get(reverse('admin_backup_download', kwargs={'filename': self.test_filename}))
        self.assertEqual(response.status_code, 403)

    def test_download_backup_path_traversal_blocked(self):
        self.client.force_login(self.superuser)
        # Nombres no válidos por regex o que intenten path traversal
        response = self.client.get('/admin/backups/descargar/nonexistent_backup.sql.gz/')
        self.assertEqual(response.status_code, 404)

    def test_download_backup_superuser_success(self):
        from django.urls import reverse
        from apps.usuarios.models import LogAuditoria
        self.client.force_login(self.superuser)
        with patch.object(BackupService, 'get_backup_dir', return_value=Path(self.temp_dir)):
            response = self.client.get(reverse('admin_backup_download', kwargs={'filename': self.test_filename}))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/gzip')
            self.assertIn(f'attachment; filename="{self.test_filename}"', response['Content-Disposition'])

            # Verificar integridad de bytes descargados
            downloaded_bytes = b"".join(response.streaming_content)
            decompressed = gzip.decompress(downloaded_bytes).decode('utf-8')
            self.assertEqual(decompressed, "-- Test backup content")

            # Verificar auditoría
            log = LogAuditoria.objects.filter(accion='DESCARGA_BACKUP').first()
            self.assertIsNotNone(log)
            self.assertEqual(log.usuario, self.superuser)
            self.assertEqual(log.datos_nuevos['archivo'], self.test_filename)

    def test_admin_changelist_proxy_model_renders(self):
        self.client.force_login(self.superuser)
        with patch.object(BackupService, 'get_backup_dir', return_value=Path(self.temp_dir)):
            response = self.client.get('/admin/usuarios/respaldobasedatos/')
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Copias de Seguridad de Base de Datos')
