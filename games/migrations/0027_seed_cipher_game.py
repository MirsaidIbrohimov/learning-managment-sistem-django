"""🔐 "Shifrni Och" öyini va boşlanğiç jumboqlar.

Kalit va tokenlar bu yerda hisoblanmaydi (migratsiya kod özgarişiga bog'lanib qolmasin):
CipherPuzzle.ensure_tokens() ularni birinçi öyinda yaratadi.
"""
from django.db import migrations

SLUG = 'shifrni-och'

PUZZLES = [
    # (matn, shifr, qiyinlik, vaqt)
    ("KOD YOZ", 'caesar', 'easy', 150),
    ("SALOM DUNYO", 'atbash', 'easy', 150),
    ("BILIM KUCH", 'caesar', 'easy', 150),
    ("XATO HAM DARS", 'caesar', 'medium', 180),
    ("HTML", 'morse', 'medium', 150),
    ("KOMPYUTER", 'morse', 'medium', 180),
    ("CODE", 'binary', 'medium', 150),
    ("BIT VA BAYT", 'binary', 'medium', 180),
    ("PYTHON ILON EMAS", 'atbash', 'medium', 180),
    ("DASTURCHI HAR KUNI O'RGANADI", 'substitution', 'hard', 300),
    ("ALGORITM BU QADAMLAR KETMA-KETLIGI", 'substitution', 'hard', 300),
    ("INTERNET BU TARMOQLAR TARMOG'I", 'substitution', 'hard', 300),
]


def seed(apps, schema_editor):
    Game = apps.get_model('games', 'Game')
    CipherPuzzle = apps.get_model('games', 'CipherPuzzle')
    game, created = Game.objects.get_or_create(slug=SLUG, defaults={
        'title': "Shifrni Och",
        'description': "Shifrlangan xabarni oçing! Sezar, Atbaş, Morze, ikkilik kod va tasodifiy almaştiriş — "
                       "har bir belgiga harf qöying, ishoralardan foydalaning va eng yuqori ballni oling.",
        'game_type': 'cipher',
        'icon': 'bi-shield-lock',
    })
    if not created:
        return
    for order, (text, kind, difficulty, limit) in enumerate(PUZZLES):
        CipherPuzzle.objects.create(game=game, plaintext=text, cipher_type=kind,
                                    difficulty=difficulty, time_limit=limit, order=order)


def unseed(apps, schema_editor):
    apps.get_model('games', 'Game').objects.filter(slug=SLUG, game_type='cipher').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0026_cipher_game'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
