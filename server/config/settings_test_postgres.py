"""
Configuración de pruebas para CU-35 con PostgreSQL local aislado.

Apunta exclusivamente a la base de datos `kantu_ml_test` en localhost:5433.
Nunca utiliza Neon ni credenciales de producción.
"""

from .settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('ML_TEST_DB_NAME', default='kantu_ml_test'),
        'USER': env('ML_TEST_DB_USER', default='postgres'),
        'PASSWORD': env('ML_TEST_DB_PASSWORD', default='postgres'),
        'HOST': env('ML_TEST_DB_HOST', default='localhost'),
        'PORT': env('ML_TEST_DB_PORT', default='5433'),
        'CONN_MAX_AGE': 0,
        'OPTIONS': {
            'sslmode': 'prefer',
            'channel_binding': 'prefer',
        },
    }
}

# Desactivar servicios externos en pruebas
CLOUDINARY_CLOUD_NAME = ''
CLOUDINARY_API_KEY = ''
CLOUDINARY_API_SECRET = ''
STRIPE_SECRET_KEY = ''
STRIPE_PUBLISHABLE_KEY = ''
STRIPE_WEBHOOK_SECRET = ''
OPENAI_API_KEY = ''
OPENAI_MODEL = 'gpt-test'

ALLOWED_HOSTS = ['*']
