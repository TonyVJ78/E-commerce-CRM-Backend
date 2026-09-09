import os
import sys
from pathlib import Path

# Add 'server' directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
SERVER_DIR = BASE_DIR / 'server'
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Initialize Django WSGI application
from django.core.wsgi import get_wsgi_application

app = get_wsgi_application()
