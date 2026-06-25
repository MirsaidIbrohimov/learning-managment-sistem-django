import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.template.loader import get_template
for t in ['accounts/chat/_messenger_styles.html', 'accounts/chat/_messenger_script.html', 'accounts/chat/messenger.html']:
    try:
        get_template(t)
        print('OK', t)
    except Exception as e:
        print('ERR', t, repr(e))
