"""Optional deployment entry point; retains the project's config.settings."""
from config.settings import *  # noqa: F403,F401
from django.core.exceptions import ImproperlyConfigured

if DEBUG:  # noqa: F405
    raise ImproperlyConfigured('Production uçun .env da DEBUG=False bölişi şart.')
