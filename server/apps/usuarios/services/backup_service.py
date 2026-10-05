"""
Servicio central de Respaldo y Restauración de Base de Datos para Kantu Market.
Soporte para Neon PostgreSQL Cloud con motor híbrido (pg_dump nativo + fallback Python).
"""

import datetime
import gzip
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass
class DatabaseCredentials:
    """Contenedor de credenciales resueltas para PostgreSQL."""
    name: str
    user: str
    password: str
    host: str
    port: int = 5432
    sslmode: str = 'require'
    endpoint_id: str = ''
    extra_options: str = ''

    @classmethod
    def from_settings(cls, alias: str = 'default') -> 'DatabaseCredentials':
        """Extrae credenciales desde settings.DATABASES o DATABASE_URL."""
        db_conf = settings.DATABASES.get(alias, {})
        
        # 1. Intentar desde DATABASE_URL si está en entorno
        db_url = os.environ.get('DATABASE_URL')
        if db_url:
            try:
                parsed = urllib.parse.urlparse(db_url)
                query = urllib.parse.parse_qs(parsed.query)
                host = parsed.hostname or 'localhost'
                endpoint = ''
                if 'neon.tech' in host and host.startswith('ep-'):
                    endpoint = host.split('.')[0]
                elif 'options' in query:
                    opts = query['options'][0]
                    m = re.search(r'endpoint=([a-zA-Z0-9_-]+)', opts)
                    if m:
                        endpoint = m.group(1)

                return cls(
                    name=parsed.path.lstrip('/') or 'postgres',
                    user=parsed.username or 'postgres',
                    password=parsed.password or '',
                    host=host,
                    port=parsed.port or 5432,
                    sslmode=query.get('sslmode', ['require'])[0],
                    endpoint_id=endpoint,
                    extra_options=query.get('options', [''])[0],
                )
            except Exception as e:
                logger.warning('No se pudo parsear DATABASE_URL: %s. Usando DATABASES[default].', e)

        # 2. Extraer desde settings.DATABASES[alias]
        host = db_conf.get('HOST', 'localhost')
        endpoint = ''
        if 'neon.tech' in host and host.startswith('ep-'):
            endpoint = host.split('.')[0]

        options = db_conf.get('OPTIONS', {})
        sslmode = options.get('sslmode', 'require')
        raw_options = options.get('options', '')
        if not endpoint and 'endpoint=' in raw_options:
            m = re.search(r'endpoint=([a-zA-Z0-9_-]+)', raw_options)
            if m:
                endpoint = m.group(1)

        return cls(
            name=db_conf.get('NAME', 'kantu_market'),
            user=db_conf.get('USER', 'postgres'),
            password=db_conf.get('PASSWORD', ''),
            host=host,
            port=int(db_conf.get('PORT') or 5432),
            sslmode=sslmode,
            endpoint_id=endpoint,
            extra_options=raw_options,
        )


class BinaryDetector:
    """Detección heurística de utilitarios nativos de PostgreSQL en el sistema operativo."""

    @staticmethod
    def find_binary(binary_name: str) -> Optional[str]:
        """Busca el ejecutable en PATH y en ubicaciones estándar de Windows y Linux."""
        # 1. Búsqueda en PATH
        in_path = shutil.which(binary_name)
        if in_path:
            return in_path

        # 2. Rutas conocidas en Windows
        if sys.platform == 'win32':
            exe_name = f"{binary_name}.exe" if not binary_name.endswith('.exe') else binary_name
            windows_candidates = [
                Path(r"C:\Program Files\PostgreSQL"),
                Path(r"C:\Program Files (x86)\PostgreSQL"),
                Path(r"C:\PostgreSQL"),
                Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "PostgreSQL",
            ]
            for base_dir in windows_candidates:
                if base_dir.is_dir():
                    for match in base_dir.glob(f"*/bin/{exe_name}"):
                        if match.is_file():
                            return str(match)

        # 3. Rutas conocidas en Linux / macOS
        else:
            linux_candidates = [
                "/usr/lib/postgresql",
                "/usr/local/opt/libpq/bin",
                "/usr/local/bin",
                "/usr/bin",
            ]
            for base in linux_candidates:
                p = Path(base)
                if p.is_dir():
                    if (p / binary_name).is_file():
                        return str(p / binary_name)
                    for match in p.glob(f"*/bin/{binary_name}"):
                        if match.is_file():
                            return str(match)

        return None


class BackupService:
    """Servicio orquestador de respaldo y restauración de base de datos."""

    @classmethod
    def get_backup_dir(cls, custom_dir: Optional[str] = None) -> Path:
        """Obtiene la ruta absoluta del directorio de respaldos asegurando su existencia."""
        if custom_dir:
            backup_path = Path(custom_dir).resolve()
        else:
            backup_path = Path(settings.BASE_DIR) / 'backups'

        backup_path.mkdir(parents=True, exist_ok=True)
        return backup_path

    @classmethod
    def create_backup(
        cls,
        output_dir: Optional[str] = None,
        engine: str = 'auto',
        keep: int = 7,
        tag: str = '',
        user: Any = None,
    ) -> Dict[str, Any]:
        """
        Genera un respaldo completo de la base de datos en formato .sql.gz.

        Args:
            output_dir: Carpeta destino. Por defecto `server/backups/`.
            engine: 'auto', 'native' (pg_dump) o 'python' (fallback psycopg/django).
            keep: Cantidad de copias a retener (rotación FIFO).
            tag: Sufijo opcional para el nombre del archivo.
            user: Instancia de Usuario para bitácora de auditoría.

        Returns:
            Dict con métricas del respaldo generado.
        """
        start_time = time.time()
        now = timezone.now()
        timestamp_str = now.strftime('%Y%m%d_%H%M%S')
        tag_suffix = f"_{tag.strip()}" if tag.strip() else ""
        filename = f"backup_kantu_{timestamp_str}{tag_suffix}.sql.gz"

        backup_dir = cls.get_backup_dir(output_dir)
        target_file = backup_dir / filename

        creds = DatabaseCredentials.from_settings()
        pg_dump_bin = BinaryDetector.find_binary('pg_dump')

        # Determinar motor
        resolved_engine = engine.lower()
        if resolved_engine == 'auto':
            resolved_engine = 'native' if pg_dump_bin else 'python'
        elif resolved_engine == 'native' and not pg_dump_bin:
            raise RuntimeError(
                "Motor 'native' solicitado pero 'pg_dump' no fue encontrado en PATH ni en directorios estándar. "
                "Utilice --engine=python o instale PostgreSQL client tools."
            )

        logger.info('Iniciando respaldo de base de datos [%s] con motor [%s] -> %s', creds.name, resolved_engine, filename)

        tables_count = 0
        rows_count = 0

        if resolved_engine == 'native':
            cls._create_native_backup(creds, pg_dump_bin, target_file)
        else:
            tables_count, rows_count = cls._create_python_backup(creds, target_file, now)

        filesize = target_file.stat().st_size
        duration = round(time.time() - start_time, 2)

        # Aplicar rotación y retención
        deleted_files = cls.rotate_backups(backup_dir, keep=keep)

        # Registrar en auditoría
        cls._log_auditoria(
            accion='BACKUP',
            detalles={
                'archivo': filename,
                'tamano_bytes': filesize,
                'tamano_humano': cls._format_bytes(filesize),
                'motor': resolved_engine,
                'duracion_segundos': duration,
                'tablas': tables_count,
                'filas_aproximadas': rows_count,
                'retencion_keep': keep,
                'archivos_rotados': deleted_files,
            },
            user=user,
        )

        return {
            'success': True,
            'filename': filename,
            'filepath': str(target_file),
            'filesize': filesize,
            'filesize_human': cls._format_bytes(filesize),
            'engine': resolved_engine,
            'duration_seconds': duration,
            'tables_count': tables_count,
            'rows_count': rows_count,
            'deleted_files': deleted_files,
            'timestamp': now.isoformat(),
        }

    @classmethod
    def _create_native_backup(cls, creds: DatabaseCredentials, pg_dump_bin: str, target_file: Path) -> None:
        """Genera el volcado utilizando el comando pg_dump nativo y compresión gzip."""
        env = os.environ.copy()
        env['PGPASSWORD'] = creds.password
        env['PGSSLMODE'] = creds.sslmode

        cmd = [
            pg_dump_bin,
            '-h', creds.host,
            '-p', str(creds.port),
            '-U', creds.user,
            '-d', creds.name,
            '--no-owner',
            '--no-privileges',
            '--clean',
            '--if-exists',
            '--format=plain',
        ]

        if creds.endpoint_id:
            cmd.extend(['--options', f"endpoint={creds.endpoint_id}"])

        with gzip.open(target_file, 'wb', compresslevel=9) as gz_out:
            proc = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = proc.communicate()

            if proc.returncode != 0:
                target_file.unlink(missing_ok=True)
                error_msg = stderr.decode('utf-8', errors='replace')
                raise RuntimeError(f"Fallo en pg_dump (código {proc.returncode}): {error_msg}")

            gz_out.write(stdout)

    @classmethod
    def _create_python_backup(
        cls,
        creds: DatabaseCredentials,
        target_file: Path,
        now: datetime.datetime,
    ) -> Tuple[int, int]:
        """
        Motor autónomo en Python: genera un script SQL reproducible con control explícito
        de triggers, secuencias y orden topológico, comprimido en streaming .sql.gz.
        """
        with connection.cursor() as cursor:
                # 1. Obtener lista de tablas públicas ordenadas topológicamente
                tables = cls._get_topological_tables(cursor)
                # 2. Obtener lista de secuencias
                sequences = cls._get_sequences(cursor)
                # 3. Obtener tablas con triggers de usuario activos
                cursor.execute("""
                    SELECT DISTINCT event_object_table
                    FROM information_schema.triggers
                    WHERE trigger_schema = 'public';
                """)
                trigger_tables = [r[0] for r in cursor.fetchall()]

                total_tables = len(tables)
                total_rows = 0

                with gzip.open(target_file, 'wt', encoding='utf-8', compresslevel=9) as gz:
                    # Escribir cabecera
                    gz.write("-- ==============================================================================\n")
                    gz.write("-- Kantu Market — Respaldo de Base de Datos PostgreSQL (Neon Cloud)\n")
                    gz.write(f"-- Fecha de Generación: {now.isoformat()}\n")
                    gz.write(f"-- Base de Datos: {creds.name} | Host: {creds.host}\n")
                    gz.write(f"-- Motor: python-psycopg-fallback (Compresión gzip)\n")
                    gz.write(f"-- Total Tablas: {total_tables} | Total Secuencias: {len(sequences)}\n")
                    gz.write("-- ==============================================================================\n\n")

                    gz.write("SET statement_timeout = 0;\n")
                    gz.write("SET lock_timeout = 0;\n")
                    gz.write("SET client_encoding = 'UTF8';\n")
                    gz.write("SET standard_conforming_strings = on;\n")
                    gz.write("SET check_function_bodies = false;\n")
                    gz.write("SET client_min_messages = warning;\n\n")

                    # Paso 1: Desactivar triggers de usuario
                    gz.write("-- ------------------------------------------------------------------------------\n")
                    gz.write("-- 1. DESACTIVAR TRIGGERS DE NEGOCIO (Evita colisiones de stock y bitácoras)\n")
                    gz.write("-- ------------------------------------------------------------------------------\n")
                    gz.write("BEGIN;\n")
                    for tbl in trigger_tables:
                        gz.write(f'ALTER TABLE "{tbl}" DISABLE TRIGGER USER;\n')
                    gz.write("COMMIT;\n\n")

                    # Paso 2: Limpieza de datos (TRUNCATE en cascada)
                    gz.write("-- ------------------------------------------------------------------------------\n")
                    gz.write("-- 2. LIMPIEZA PREVIA Y CARGA DE DATOS EN ORDEN TOPOLÓGICO\n")
                    gz.write("-- ------------------------------------------------------------------------------\n")
                    gz.write("BEGIN;\n")
                    if tables:
                        tables_quoted = ", ".join(f'"{t}"' for t in reversed(tables))
                        gz.write(f"TRUNCATE TABLE {tables_quoted} CASCADE;\n\n")

                    # Paso 3: Volcado de datos por tabla
                    for tbl in tables:
                        cursor.execute("""
                            SELECT column_name, data_type, udt_name
                            FROM information_schema.columns
                            WHERE table_name = %s AND table_schema = 'public';
                        """, [tbl])
                        col_types = {r[0]: r[1] for r in cursor.fetchall()}

                        cursor.execute(f'SELECT * FROM "{tbl}";')
                        col_names = [col[0] for col in cursor.description]
                        cols_str = ", ".join(f'"{c}"' for c in col_names)

                        batch_size = 500
                        table_rows = 0

                        while True:
                            rows = cursor.fetchmany(batch_size)
                            if not rows:
                                break

                            values_list = []
                            for row in rows:
                                escaped_vals = [
                                    cls._format_sql_value(v, is_array=(col_types.get(c) == 'ARRAY'))
                                    for c, v in zip(col_names, row)
                                ]
                                values_list.append(f"({', '.join(escaped_vals)})")

                            gz.write(f'INSERT INTO "{tbl}" ({cols_str}) VALUES\n')
                            gz.write(",\n".join(values_list))
                            gz.write(";\n")

                            table_rows += len(rows)
                            total_rows += len(rows)

                        if table_rows > 0:
                            gz.write(f"-- Tabla \"{tbl}\": {table_rows} filas restauradas.\n\n")

                    # Cerrar transacción de datos para liberar eventos diferidos
                    gz.write("COMMIT;\n\n")

                    # Paso 4: Sincronización de secuencias
                    gz.write("-- ------------------------------------------------------------------------------\n")
                    gz.write("-- 3. SINCRONIZACIÓN DE SECUENCIAS (setval)\n")
                    gz.write("-- ------------------------------------------------------------------------------\n")
                    gz.write("BEGIN;\n")
                    for seq in sequences:
                        try:
                            cursor.execute(f'SELECT last_value, is_called FROM "{seq}";')
                            res = cursor.fetchone()
                            if res:
                                last_val, is_called = res
                                gz.write(f"SELECT pg_catalog.setval('public.\"{seq}\"', {last_val}, {str(is_called).lower()});\n")
                        except Exception as e:
                            logger.warning('No se pudo leer la secuencia %s: %s', seq, e)

                    # Bloque dinámico para garantizar alineación de secuencias con MAX(id)
                    gz.write("\n-- Resincronización dinámica de secuencias según valores máximos reales:\n")
                    gz.write("DO $$\n")
                    gz.write("DECLARE\n")
                    gz.write("    r RECORD;\n")
                    gz.write("BEGIN\n")
                    gz.write("    FOR r IN (\n")
                    gz.write("        SELECT table_name, column_name, pg_get_serial_sequence('\"' || table_name || '\"', column_name) as seq_name\n")
                    gz.write("        FROM information_schema.columns\n")
                    gz.write("        WHERE table_schema = 'public'\n")
                    gz.write("          AND pg_get_serial_sequence('\"' || table_name || '\"', column_name) IS NOT NULL\n")
                    gz.write("    ) LOOP\n")
                    gz.write("        EXECUTE format('SELECT setval(%L, COALESCE((SELECT MAX(%I) FROM %I), 1), (SELECT MAX(%I) IS NOT NULL FROM %I))',\n")
                    gz.write("            r.seq_name, r.column_name, r.table_name, r.column_name, r.table_name);\n")
                    gz.write("    END LOOP;\n")
                    gz.write("END $$;\n")
                    gz.write("COMMIT;\n\n")

                    # Paso 5: Reactivación de triggers
                    gz.write("-- ------------------------------------------------------------------------------\n")
                    gz.write("-- 4. REACTIVACIÓN DE TRIGGERS DE NEGOCIO\n")
                    gz.write("-- ------------------------------------------------------------------------------\n")
                    gz.write("BEGIN;\n")
                    for tbl in trigger_tables:
                        gz.write(f'ALTER TABLE "{tbl}" ENABLE TRIGGER USER;\n')
                    gz.write("COMMIT;\n\n")
                    gz.write("-- Fin del respaldo Kantu Market.\n")

        return total_tables, total_rows

    @classmethod
    def restore_backup(
        cls,
        filepath: str,
        engine: str = 'auto',
        skip_safety_checks: bool = False,
        user: Any = None,
    ) -> Dict[str, Any]:
        """
        Ejecuta la restauración íntegra de un respaldo .sql.gz o .sql en la base de datos.
        Asegura desactivación preventiva de triggers y resincronización de secuencias.
        """
        start_time = time.time()
        backup_path = Path(filepath).resolve()

        if not backup_path.is_file():
            raise FileNotFoundError(f"El archivo de respaldo no existe: {backup_path}")

        creds = DatabaseCredentials.from_settings()
        psql_bin = BinaryDetector.find_binary('psql')

        resolved_engine = engine.lower()
        if resolved_engine == 'auto':
            resolved_engine = 'native' if psql_bin else 'python'
        elif resolved_engine == 'native' and not psql_bin:
            raise RuntimeError("psql nativo no disponible. Use --engine=python.")

        logger.info('Iniciando restauración de base de datos desde: %s con motor: %s', backup_path.name, resolved_engine)

        # Descomprimir contenido SQL
        if backup_path.suffix == '.gz' or backup_path.name.endswith('.sql.gz'):
            with gzip.open(backup_path, 'rt', encoding='utf-8') as f:
                sql_content = f.read()
        else:
            with open(backup_path, 'r', encoding='utf-8') as f:
                sql_content = f.read()

        if not sql_content.strip():
            raise ValueError("El archivo de respaldo está vacío.")

        # Ejecución
        if resolved_engine == 'native' and psql_bin:
            cls._restore_native(creds, psql_bin, sql_content)
        else:
            cls._restore_python(sql_content)

        duration = round(time.time() - start_time, 2)

        # Registrar en auditoría
        cls._log_auditoria(
            accion='RESTAURACION',
            detalles={
                'archivo': backup_path.name,
                'tamano_bytes': backup_path.stat().st_size,
                'motor': resolved_engine,
                'duracion_segundos': duration,
                'fecha_restauracion': timezone.now().isoformat(),
            },
            user=user,
        )

        return {
            'success': True,
            'filename': backup_path.name,
            'filepath': str(backup_path),
            'engine': resolved_engine,
            'duration_seconds': duration,
        }

    @classmethod
    def _restore_native(cls, creds: DatabaseCredentials, psql_bin: str, sql_content: str) -> None:
        """Restaura usando el binario psql."""
        env = os.environ.copy()
        env['PGPASSWORD'] = creds.password
        env['PGSSLMODE'] = creds.sslmode

        cmd = [
            psql_bin,
            '-h', creds.host,
            '-p', str(creds.port),
            '-U', creds.user,
            '-d', creds.name,
            '-v', 'ON_ERROR_STOP=1',
        ]
        if creds.endpoint_id:
            cmd.extend(['--options', f"endpoint={creds.endpoint_id}"])

        proc = subprocess.Popen(
            cmd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
        )
        stdout, stderr = proc.communicate(input=sql_content)

        if proc.returncode != 0:
            raise RuntimeError(f"Error durante psql (código {proc.returncode}): {stderr}")

    @classmethod
    def _restore_python(cls, sql_content: str) -> None:
        """
        Ejecuta la restauración de forma segura directamente sobre la conexión PostgreSQL,
        con manejo estricto de triggers y bloques transaccionales.
        """
        old_autocommit = connection.get_autocommit()
        connection.set_autocommit(True)
        try:
            with connection.cursor() as cursor:
                # Obtener tablas con triggers de usuario para salvaguarda en caso de fallo
                cursor.execute("""
                    SELECT DISTINCT event_object_table
                    FROM information_schema.triggers
                    WHERE trigger_schema = 'public';
                """)
                trigger_tables = [r[0] for r in cursor.fetchall()]

                # 1. Desactivación preventiva explícita de triggers de usuario
                for tbl in trigger_tables:
                    try:
                        cursor.execute(f'ALTER TABLE "{tbl}" DISABLE TRIGGER USER;')
                    except Exception as e:
                        logger.debug('No se pudo desactivar triggers en %s: %s', tbl, e)

                try:
                    # 2. Ejecutar el script SQL completo
                    cursor.execute(sql_content)
                finally:
                    # 3. Reactivación obligatoria de triggers de usuario
                    for tbl in trigger_tables:
                        try:
                            cursor.execute(f'ALTER TABLE "{tbl}" ENABLE TRIGGER USER;')
                        except Exception as e:
                            logger.warning('No se pudo reactivar triggers en %s: %s', tbl, e)
        finally:
            connection.set_autocommit(old_autocommit)

    @classmethod
    def list_backups(cls, directory: Optional[Path] = None) -> List[Dict[str, Any]]:
        """Lista los archivos de respaldo disponibles en el directorio."""
        backup_dir = directory or cls.get_backup_dir()
        if not backup_dir.is_dir():
            return []

        backups = []
        pattern = re.compile(r'^backup_kantu_(\d{8}_\d{6})(?:_(.*))?\.sql\.gz$')

        for item in backup_dir.glob('backup_kantu_*.sql.gz'):
            stat = item.stat()
            match = pattern.match(item.name)
            ts_str = match.group(1) if match else ''
            tag = match.group(2) if (match and match.group(2)) else ''

            backups.append({
                'filename': item.name,
                'filepath': str(item),
                'size_bytes': stat.st_size,
                'size_human': cls._format_bytes(stat.st_size),
                'created_at': datetime.datetime.fromtimestamp(stat.st_mtime, tz=datetime.timezone.utc).isoformat(),
                'timestamp_raw': stat.st_mtime,
                'tag': tag,
            })

        backups.sort(key=lambda x: x['timestamp_raw'], reverse=True)
        return backups

    @classmethod
    def rotate_backups(cls, directory: Path, keep: int = 7) -> List[str]:
        """Elimina los respaldos más antiguos que superen el límite de retención `keep`."""
        if keep <= 0:
            return []

        all_backups = cls.list_backups(directory)
        deleted = []

        if len(all_backups) > keep:
            excess = all_backups[keep:]
            for b in excess:
                try:
                    p = Path(b['filepath'])
                    if p.is_file():
                        p.unlink()
                        deleted.append(b['filename'])
                        logger.info('Rotación FIFO: eliminado respaldo antiguo %s', b['filename'])
                except Exception as e:
                    logger.error('Error al rotar respaldo %s: %s', b['filename'], e)

        return deleted

    @classmethod
    def _get_topological_tables(cls, cursor: Any) -> List[str]:
        """Calcula el orden topológico de las tablas de la base de datos basándose en sus Foreign Keys."""
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)
        all_tables = [r[0] for r in cursor.fetchall()]

        cursor.execute("""
            SELECT
                tc.table_name AS dependent_table,
                ccu.table_name AS referenced_table
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'public'
            GROUP BY tc.table_name, ccu.table_name;
        """)
        fk_relations = cursor.fetchall()

        # Construir grafo de dependencias
        deps: Dict[str, set] = {t: set() for t in all_tables}
        for dep_tbl, ref_tbl in fk_relations:
            if dep_tbl in deps and ref_tbl in deps and dep_tbl != ref_tbl:
                deps[dep_tbl].add(ref_tbl)

        # Ordenamiento topológico
        ordered: List[str] = []
        visited = set()
        visiting = set()

        def visit(node: str):
            if node in visiting:
                return  # Romper ciclo
            if node not in visited:
                visiting.add(node)
                for parent in deps.get(node, ()):
                    visit(parent)
                visiting.remove(node)
                visited.add(node)
                ordered.append(node)

        for tbl in all_tables:
            visit(tbl)

        return ordered

    @classmethod
    def _get_sequences(cls, cursor: Any) -> List[str]:
        """Obtiene todas las secuencias del esquema público."""
        cursor.execute("""
            SELECT c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'S' AND n.nspname = 'public'
            ORDER BY c.relname;
        """)
        return [r[0] for r in cursor.fetchall()]

    @classmethod
    def _format_sql_value(cls, val: Any, is_array: bool = False) -> str:
        """Convierte tipos de Python a literales SQL seguros para PostgreSQL."""
        if val is None:
            return 'NULL'

        if is_array:
            if isinstance(val, (list, tuple)):
                if not val:
                    return "'{}'"
                items = []
                for item in val:
                    item_str = str(item).replace('\\', '\\\\').replace('"', '\\"')
                    items.append(f'"{item_str}"')
                return f"'{{{','.join(items)}}}'"
            if isinstance(val, str):
                if val == '[]':
                    return "'{}'"
                val_escaped = val.replace("'", "''")
                return f"'{val_escaped}'"

        if isinstance(val, bool):
            return 'TRUE' if val else 'FALSE'
        if isinstance(val, (int, float)):
            return str(val)
        if isinstance(val, (dict, list)):
            json_str = json.dumps(val, default=str).replace("'", "''")
            return f"'{json_str}'"
        if isinstance(val, (datetime.datetime, datetime.date, datetime.time)):
            return f"'{val.isoformat()}'"
        if isinstance(val, (bytes, memoryview)):
            hex_data = bytes(val).hex()
            return f"E'\\\\x{hex_data}'"

        # Fallback a string
        escaped = str(val).replace("'", "''")
        return f"'{escaped}'"

    @classmethod
    def _format_bytes(cls, num_bytes: int) -> str:
        """Formatea un número de bytes a formato legible (KB, MB, GB)."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if abs(num_bytes) < 1024.0:
                return f"{num_bytes:3.1f} {unit}"
            num_bytes /= 1024.0
        return f"{num_bytes:.1f} PB"

    @classmethod
    def _log_auditoria(cls, accion: str, detalles: Dict[str, Any], user: Any = None) -> None:
        """Registra la operación en la tabla log_auditoria si el modelo existe."""
        try:
            from apps.usuarios.models import LogAuditoria
            LogAuditoria.objects.create(
                usuario=user if (user and getattr(user, 'is_authenticated', False)) else None,
                tabla_afectada='database',
                registro_id=0,
                accion=accion,
                datos_anteriores=None,
                datos_nuevos=detalles,
            )
        except Exception as e:
            logger.warning('No se pudo registrar la operación de backup en LogAuditoria: %s', e)
