"""Configuración exclusiva para la validación E2E local de CU-35.

Nunca lee DB_*: usa PostgreSQL local y la base separada ``kantu_ml_e2e``.
El nombre puede cambiarse solo con ML_E2E_DB_NAME.
"""

from .settings_test_postgres import *  # noqa: F401,F403

DATABASES['default']['NAME'] = env('ML_E2E_DB_NAME', default='kantu_ml_e2e')
