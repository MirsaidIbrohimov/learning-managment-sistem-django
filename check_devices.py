import django, os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
django.setup()
from accounts.models import UserDevice, UserSession
from django.db.models import Count

print('=== FAOL QURILMALAR ===')
for d in UserDevice.objects.filter(is_active=True).select_related('user'):
    sessions = d.sessions.filter(is_active=True).count()
    print(f'  User: {d.user.username} | {d.device_name} | {d.device_type} | Sessions: {sessions}')

print()
print('=== FAOL SESSIYALAR ===')
for s in UserSession.objects.filter(is_active=True).select_related('user', 'device'):
    dev = s.device.device_name if s.device else 'None'
    print(f'  User: {s.user.username} | {dev} | expired: {s.is_expired}')

print()
print('=== USER QURILMA SONI ===')
for row in UserDevice.objects.filter(is_active=True).values('user__username').annotate(cnt=Count('id')).order_by('-cnt'):
    uname = row['user__username']
    cnt = row['cnt']
    print(f'  {uname}: {cnt} ta')

print()
print('=== JAMI ===')
print(f'Faol devices: {UserDevice.objects.filter(is_active=True).count()}')
print(f'Faol sessions: {UserSession.objects.filter(is_active=True).count()}')
print(f'Jami devices: {UserDevice.objects.count()}')
print(f'Jami sessions: {UserSession.objects.count()}')
