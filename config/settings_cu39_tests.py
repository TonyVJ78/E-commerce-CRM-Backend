"""Pruebas CU-39 con PostgreSQL local; no utilizar para servir la aplicación.

No carga credenciales productivas en los servicios de prueba ni admite un host
remoto de base de datos. El runner crea y elimina test_cu39_revision.
"""
import os
from .settings import *  # noqa: F403

DEBUG = False
SECRET_KEY = 'cu39-isolated-tests-only-not-a-production-key'
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
DATABASES = {'default': {
    'ENGINE': 'django.db.backends.postgresql',
    'HOST': '127.0.0.1',
    'PORT': os.environ.get('CU39_TEST_DB_PORT', '55439'),
    'NAME': 'cu39_revision',
    'USER': os.environ.get('CU39_TEST_DB_USER', 'cu39_test'),
    'PASSWORD': os.environ.get('CU39_TEST_DB_PASSWORD', ''),
    'OPTIONS': {'sslmode': 'disable'},
    'TEST': {'NAME': 'test_cu39_revision'},
}}
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
# Aceleración exclusiva de pruebas automáticas; no usar en cuentas humanas.
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
FCM_ENABLED = False
FIREBASE_CREDENTIALS_FILE = ''
ANTHROPIC_API_KEY = ''
OPENAI_API_KEY = ''
AI_RECOMMENDATIONS_ENABLED = False
STRIPE_SECRET_KEY = ''
STRIPE_PUBLISHABLE_KEY = ''
STRIPE_WEBHOOK_SECRET = ''
CRON_SECRET = ''
CLOUDINARY_CLOUD_NAME = 'cu39-fixture'
CLOUDINARY_API_KEY = 'fixture-not-real'
CLOUDINARY_API_SECRET = 'fixture-not-real'
CU39_BRL_ENABLED = False
CU39_BRL_DEMO = False
CU39_BRL_PROVIDER_APPROVED = False
CU39_BRL_MAX_AGE_DAYS = None
