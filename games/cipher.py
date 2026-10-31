"""🔐 "Shifrni Och" — shifrlaş, oçiş, ishoralar va ball hisoblaş (sof funksiyalar).

Xabar tokenlarga bölinadi: ['c', token] — shifrlangan harf (öyinçi unga harf beradi),
['s', belgi] — böşliq/tinish belgisi (özgarmaydi). Asl matn faqat serverda turadi,
mijozga faqat tokenlar yuboriladi.
"""
import random
from collections import Counter

from accounts.alphabet import to_new_alphabet

ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZÇĞÖŞ'

CIPHER_TYPES = (
    ('caesar', "Sezar (siljitiş)"),
    ('atbash', "Atbaş (teskari alifbo)"),
    ('morse', "Morze kodi"),
    ('binary', "Ikkilik kod"),
    ('substitution', "Almaştiriş (tasodifiy kalit)"),
)
CIPHER_NAMES = dict(CIPHER_TYPES)
CIPHER_EXPLAIN = {
    'caesar': "Har bir harf alifbo böyiça bir xil qadamga surilgan. Bitta harfni topsangiz — qolgani ham şu qadamda.",
    'atbash': "Alifbo teskari ağdarilgan: A ↔ Ş, B ↔ Ö, C ↔ Ğ ... Birinçi harf oxirgisi bilan almaşadi.",
    'morse': "Har bir harf nuqta (.) va çiziq (-) ketma-ketligi. E = '.', T = '-' — eng qisqa kodlar eng köp uçraydi.",
    'binary': "Har bir harf — uning kompyuterdagi kodi (ASCII/Unicode) ikkilik sanoq tizimida. A = 65 = 01000001.",
    'substitution': "Har bir harf boşqa tasodifiy harf bilan almaştirilgan. Eng köp uçraydigan harflar va qisqa sözlardan boşlang.",
}

ALPHABET_ORDER = ' (alifbo: ' + ' '.join(ALPHABET) + ')'
CIPHER_EXPLAIN['caesar'] += ALPHABET_ORDER
CIPHER_EXPLAIN['atbash'] += ALPHABET_ORDER

MORSE = {
    'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.', 'F': '..-.', 'G': '--.', 'H': '....',
    'I': '..', 'J': '.---', 'K': '-.-', 'L': '.-..', 'M': '--', 'N': '-.', 'O': '---', 'P': '.--.',
    'Q': '--.-', 'R': '.-.', 'S': '...', 'T': '-', 'U': '..-', 'V': '...-', 'W': '.--', 'X': '-..-',
    'Y': '-.--', 'Z': '--..', 'Ç': '-.-..', 'Ğ': '--.-.', 'Ö': '---.', 'Ş': '.--..',
}

BASE_SCORE = {'easy': 100, 'medium': 200, 'hard': 300}
SOLVE_COINS = {'easy': 3, 'medium': 5, 'hard': 8}
HINT_PENALTY = 0.2
MIN_MULTIPLIER = 0.2
WRONG_CHECK_PENALTY = 5
TIME_BONUS_SHARE = 0.5
PREMIUM_FREE_HINTS = 1


def normalize(text):
    """Yangi alifbo + katta harflar + bitta böşliq."""
    return ' '.join(to_new_alphabet(text or '').upper().split())


def random_key(cipher_type, rng=random):
    if cipher_type == 'caesar':
        return {'shift': rng.randint(1, len(ALPHABET) - 1)}
    if cipher_type == 'substitution':
        letters = list(ALPHABET)
        while True:
            rng.shuffle(letters)
            if all(a != b for a, b in zip(ALPHABET, letters)):  # heç bir harf özi bilan qolmasin
                return {'perm': ''.join(letters)}
    return {}


def _letter_token(ch, cipher_type, key):
    i = ALPHABET.index(ch)
    if cipher_type == 'caesar':
        return ALPHABET[(i + int(key.get('shift', 3))) % len(ALPHABET)]
    if cipher_type == 'atbash':
        return ALPHABET[len(ALPHABET) - 1 - i]
    if cipher_type == 'substitution':
        return key['perm'][i]
    if cipher_type == 'morse':
        return MORSE[ch]
    if cipher_type == 'binary':
        return format(ord(ch), '08b')
    raise ValueError(f'Nomaʼlum shifr: {cipher_type}')


def encrypt(plaintext, cipher_type, key):
    """Matnni tokenlar röyxatiga aylantiradi (JSON'ga mos)."""
    tokens = []
    for ch in normalize(plaintext):
        if ch in ALPHABET:
            tokens.append(['c', _letter_token(ch, cipher_type, key)])
        else:
            tokens.append(['s', ch])
    return tokens


def answer_map(plaintext, tokens):
    """{token: harf} — töğri javob xaritasi."""
    plain = normalize(plaintext)
    return {tok: plain[i] for i, (kind, tok) in enumerate(tokens) if kind == 'c'}


def decode(tokens, mapping):
    mapping = mapping or {}
    out = []
    for kind, tok in tokens:
        if kind == 'c':
            out.append(str(mapping.get(tok) or '?')[:1].upper())
        else:
            out.append(tok)
    return ''.join(out)


def ciphertext(tokens):
    """Körsatiş uçun matn: Morze/ikkilikda tokenlar böşliq bilan, sözlar « / » bilan ajraladi."""
    if all(len(tok) == 1 for kind, tok in tokens if kind == 'c'):
        return ''.join(tok for _, tok in tokens)
    return ' '.join('/' if kind == 's' and tok == ' ' else tok for kind, tok in tokens)


def is_solved(plaintext, tokens, mapping):
    return decode(tokens, mapping) == normalize(plaintext)


def frequencies(tokens):
    """Mijoz paneli uçun: [(token, soni), ...] köpidan kamiga."""
    return Counter(tok for kind, tok in tokens if kind == 'c').most_common()


def hint(plaintext, tokens, cipher_type, kind, revealed, rng=random):
    """Ishora: {'text': ..., 'reveal': {token: harf}} yoki None (bu ishora endi yöq)."""
    answers = answer_map(plaintext, tokens)
    if kind == 'type':
        return {'text': f"Shifr turi: {CIPHER_NAMES[cipher_type]}. {CIPHER_EXPLAIN[cipher_type]}", 'reveal': {}}
    hidden = [tok for tok, _ in frequencies(tokens) if tok not in revealed]
    if not hidden:
        return None
    if kind == 'frequent':
        tok = hidden[0]
        return {'text': f"Eng köp uçraydigan belgi «{tok}» — bu «{answers[tok]}» harfi.", 'reveal': {tok: answers[tok]}}
    if kind == 'letter':
        tok = rng.choice(hidden)
        return {'text': f"«{tok}» — bu «{answers[tok]}» harfi.", 'reveal': {tok: answers[tok]}}
    return None


def charged_hints(hints_used, premium):
    return max(0, hints_used - (PREMIUM_FREE_HINTS if premium else 0))


def score(difficulty, charged, wrong_checks, elapsed, time_limit):
    base = BASE_SCORE.get(difficulty, BASE_SCORE['medium'])
    multiplier = max(MIN_MULTIPLIER, 1 - HINT_PENALTY * charged)
    left = max(0.0, 1 - elapsed / time_limit) if time_limit else 0.0
    total = base * multiplier + base * TIME_BONUS_SHARE * left - WRONG_CHECK_PENALTY * wrong_checks
    return max(0, round(total))


def solve_coins(difficulty, premium):
    coins = SOLVE_COINS.get(difficulty, SOLVE_COINS['medium'])
    return coins * 2 if premium else coins
