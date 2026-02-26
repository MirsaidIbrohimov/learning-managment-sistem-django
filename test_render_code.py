import django, os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
django.setup()
from accounts.templatetags.custom_filters import render_code

tests = [
    'print(5 % 2) nima chiqaradi?',
    'Python da list() va array() farqi nima?',
    'while sikli qachon toxlaydi?',
    'len("hello") nima qaytaradi?',
    '<h1> tegi nima uchun ishlatiladi?',
    'range(5) nechta element qaytaradi?',
    '`for i in range(10):` sikli necha marta ishlaydi?',
    'x == 5 shartni tekshiradi',
    'Quyidagi kodning natijasi:\n```\nx = 0\nwhile x < 3:\n    print(x)\n    x += 1\n```',
    'for kalit sozi nima?',
    'if x > 5: shartida nima tekshiriladi?',
    'Qanday qilib funksiya yaratiladi?',
    'new List() nima qaytaradi?',
    'Savollar real amaliy bolsin',
]

for t in tests:
    result = render_code(t)
    print(f'INPUT:  {t}')
    print(f'OUTPUT: {result}')
    print()
