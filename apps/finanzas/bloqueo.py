"""Serializa tasa y precios derivados sin bloquear llamadas de red."""
from contextlib import contextmanager
from django.db import connection, transaction


@contextmanager
def bloquear_cotizacion():
    with transaction.atomic():
        if connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_xact_lock(%s)', [139039])
        yield
