"""Private staging only. Do not select this module in public production."""
from config.settings import *  # noqa: F403,F401
from django.core.exceptions import ImproperlyConfigured

if not DEBUG:  # noqa: F405
    raise ImproperlyConfigured('Debug toolbar faqat yopiq DEBUG=True staging uçun.')
INSTALLED_APPS = [*INSTALLED_APPS, 'debug_toolbar']  # noqa: F405
MIDDLEWARE = ['debug_toolbar.middleware.DebugToolbarMiddleware', *MIDDLEWARE]  # noqa: F405
INTERNAL_IPS = ['127.0.0.1', '::1']
ROOT_URLCONF = 'settings.debug_urls'
