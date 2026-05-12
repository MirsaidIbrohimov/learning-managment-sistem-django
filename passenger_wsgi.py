import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# .env faylni yuklash (Passenger uchun muhim)
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / '.env')
except ImportError:
    pass

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.wsgi import get_wsgi_application

_application = get_wsgi_application()

def application(environ, start_response):
    """X-Powered-By va Server headerlarini yashiruvchi WSGI wrapper"""
    def custom_start_response(status, headers, exc_info=None):
        filtered = [(k, v) for k, v in headers if k.lower() not in ('x-powered-by', 'server')]
        return start_response(status, filtered, exc_info)
    return _application(environ, custom_start_response)
