"""Solo para el PostgreSQL desechable de work/postgres-sprint3; nunca usa .env para la conexión."""
from .settings import *  # noqa: F403

DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': 'kantu_sprint3', 'USER': 'codex_test', 'PASSWORD': '', 'HOST': '127.0.0.1', 'PORT': '55483', 'OPTIONS': {'sslmode': 'disable'}, 'TEST': {'NAME': 'test_kantu_sprint3'}}}
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
AI_RECOMMENDATIONS_ENABLED = False
FCM_ENABLED = False
