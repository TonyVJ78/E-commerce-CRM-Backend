"""
Configuración de pruebas para CU-35.

Usa SQLite en memoria (base de datos aislada y temporal) para no tocar
Neon ni ninguna base de datos de producción. Hereda todo de settings.py.
"""

from .settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Desactivar Cloudinary/Stripe/Own env en pruebas
CLOUDINARY_CLOUD_NAME = ''
CLOUDINARY_API_KEY = ''
CLOUDINARY_API_SECRET = ''
STRIPE_SECRET_KEY = ''
STRIPE_PUBLISHABLE_KEY = ''
STRIPE_WEBHOOK_SECRET = ''
OPENAI_API_KEY = ''
OPENAI_MODEL = 'gpt-test'

# Desactivar migraciones de las apps del proyecto en pruebas (usa syncdb desde
# modelos actuales) para evitar fallos preexistentes de defaults tipo lista en
# SQLite (p. ej. catalogo.0002). Solo 'ml' conserva sus migraciones nuevas.
MIGRATION_MODULES = {
    'catalogo': None,
    'pedidos': None,
    'tiendas': None,
    'usuarios': None,
    'crm': None,
    'marketing': None,
    'ia': None,
}

# Aceptar cualquier host en pruebas
ALLOWED_HOSTS = ['*']
