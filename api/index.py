import os
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent

# Check for bundled _server first, then fallback to ROOT/server
SERVER_DIR = CURRENT_DIR / '_server'
if not SERVER_DIR.exists():
    SERVER_DIR = CURRENT_DIR.parent / 'server'

ROOT_DIR = CURRENT_DIR.parent if CURRENT_DIR.name == 'api' else CURRENT_DIR

# Add server directory to Python path
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

try:
    from django.core.wsgi import get_wsgi_application
    app = get_wsgi_application()
except Exception as e:
    import traceback
    traceback.print_exc(file=sys.stderr)
    raise e
