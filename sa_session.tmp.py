"""Admin uchun brauzer sessiyasini tayyorlash (vaqtinchalik skript)."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from datetime import timedelta

from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.utils import timezone

from accounts.models import CustomUser, UserSession

user = CustomUser.objects.filter(role='admin').order_by('id').first()
print('user:', user.id, user.username, user.role)

now = timezone.now()
reuse = (UserSession.objects
         .filter(user=user, is_active=True, expires_at__gt=now)
         .order_by('-started_at').first())

key = None
if reuse and Session.objects.filter(session_key=reuse.session_key,
                                    expire_date__gt=now).exists():
    key = reuse.session_key
    print('mavjud sessiya qayta ishlatildi')

if not key:
    store = SessionStore()
    store['_auth_user_id'] = str(user.id)
    store['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
    store['_auth_user_hash'] = user.get_session_auth_hash()
    store.save()
    key = store.session_key
    UserSession.objects.create(
        user=user, session_key=key, ip_address='127.0.0.1',
        is_active=True, expires_at=now + timedelta(days=1),
    )
    print('yangi sessiya yaratildi')

cache.delete(f'active_session_{user.id}')
print('SID=' + key)
