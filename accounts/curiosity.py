"""Boş sahifadagi "Bilasizmi?" savollari.

Savollarni OpenAI töplam qilib yaratadi va ``CuriosityQuestion`` jadvaliga
saqlanadi; boş sahifa API'ni kutmaydi. Töplam haftasiga bir marta fonda
yangilanadi (yoki: ``python manage.py generate_curiosity_questions``).
Kalit yöq yoki xato bölsa — quyidagi zaxira röyxat işlaydi.

Savol har soatda va har yangi kirişda (last_login özgarganda) almaşadi.
Tugma bosilganda savol AI yordamçiga yuboriladi va javobni AI beradi;
bu xabar uçun tanga yeçilmaydi (faqat sahifada körsatilgan savol uçun).
"""
import hashlib
import json
import logging
import re
import threading
import unicodedata
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

SESSION_KEY = 'home_curiosity_question'
OPENAI_MODEL = 'gpt-4o'   # haftasiga bitta töplam; settings.CURIOSITY_OPENAI_MODEL bilan almaştirsa böladi
BATCH_SIZE = 24
POOL_SIZE = 72            # tanlov eng yangi şunça savoldan
REFRESH_HOURS = 24 * 7   # har hafta yangi töplam
POOL_CACHE_KEY = 'curiosity:pool:v2'
LOCK_KEY = 'curiosity:generating'

# kod: (nom, bootstrap icon)
CATEGORIES = {
    'history': ('Texnologiya tarixi', 'bi-hourglass-split'),
    'programming': ('Dasturlaş', 'bi-code-slash'),
    'internet': ('Internet', 'bi-globe2'),
    'security': ('Kiberxavfsizlik', 'bi-shield-lock'),
    'ai': ('Sun’iy intellekt', 'bi-cpu'),
    'hardware': ('Texnika', 'bi-motherboard'),
    'science': ('Fan', 'bi-lightbulb'),
    'people': ('Şaxslar', 'bi-person-badge'),
}

# Zaxira röyxat (OpenAI işlamaganda). Birinçi savol testlarda işlatiladi.
QUESTIONS = [
    ('people', 'Steve Jobs qaçon tuğilgan va Apple’ni qanday garajda boşlagan, bilasizmi?'),
    ('history', 'Dunyodagi birinçi kompyuter dasturçisi kim bölgan, bilasizmi?'),
    ('programming', 'Python dasturlaş tili nega aynan «Python» deb nomlangan, bilasizmi?'),
    ('internet', 'Birinçi veb-sayt qaçon va kim tomonidan yaratilgan, bilasizmi?'),
    ('programming', 'Dasturdagi xatoni nega «bug» (haşarot) deb ataşadi, bilasizmi?'),
    ('internet', 'Google nomi qaysi matematik sözdan kelib çiqqan, bilasizmi?'),
    ('history', 'Birinçi mobil telefon qönğiroği qaçon qilingan, bilasizmi?'),
    ('ai', '«Robot» sözi qaysi tildan va qaçon paydo bölgan, bilasizmi?'),
    ('history', 'Dunyodagi birinçi kompyuter öyini qaysi bölgan, bilasizmi?'),
    ('internet', 'Birinçi elektron xat (email) kim tomonidan yuborilgan, bilasizmi?'),
    ('ai', 'Sun’iy intellekt atamasi birinçi marta qaçon işlatilgan, bilasizmi?'),
    ('programming', 'Java dasturlaş tili nega qahva bilan boğliq nomga ega, bilasizmi?'),
    ('hardware', 'Kompyuter siçqonçasini kim ixtiro qilgan, bilasizmi?'),
    ('hardware', 'Bir bayt neçta bitdan iborat va nima uçun aynan şunça, bilasizmi?'),
    ('people', 'Bill Gates Microsoft’ni neça yoşida asos solgan, bilasizmi?'),
    ('hardware', 'Oyga uçgan «Apollo 11» kemasining kompyuteri qançalik kuçli bölgan, bilasizmi?'),
    ('security', 'Eng köp işlatiladigan zaif parol qaysi ekanini bilasizmi?'),
    ('internet', 'Internet orqali bir soniyada qança ma’lumot almaşinadi, bilasizmi?'),
    ('hardware', 'Klaviaturadagi harflar nega alifbo tartibida joylaşmagan, bilasizmi?'),
    ('programming', 'Linux operatsion tizimining ramzi nega pingvin, bilasizmi?'),
    ('internet', 'Internetga yuklangan birinçi surat nima bölgan, bilasizmi?'),
    ('science', 'MP3 formati qanday qilib musiqa hajmini 10 barobar kiçraytiradi, bilasizmi?'),
    ('people', 'Al-Xorazmiy nomidan qaysi zamonaviy IT atamasi kelib çiqqan, bilasizmi?'),
    ('science', 'Uluğbek rasadxonasi yulduzlarni qançalik aniq hisoblagan, bilasizmi?'),
    ('hardware', 'Smartfon batareyasini 100% gaça quvvatlaş zararlimi, bilasizmi?'),
    ('internet', 'Wi-Fi qisqartmasi aslida nimani anglatadi, bilasizmi?'),
    ('people', 'Elon Musk birinçi dasturini neça yoşida sotgan, bilasizmi?'),
    ('history', 'Tetris öyinini kim va qaysi mamlakatda yaratgan, bilasizmi?'),
    ('internet', 'Wikipedia’da neçta tilda maqolalar bor, bilasizmi?'),
    ('science', 'Kvant kompyuter oddiy kompyuterdan nimasi bilan farq qiladi, bilasizmi?'),
    ('science', 'GPS joylaşuvni qanday qilib metrgaça aniqlaydi, bilasizmi?'),
    ('science', 'Ekrandagi har bir rang qanday qilib 3 ta rangdan hosil böladi, bilasizmi?'),
    ('ai', 'Dunyodagi birinçi dasturlaştiriladigan robot qaçon işga tuşgan, bilasizmi?'),
    ('internet', 'YouTube’ga yuklangan birinçi video nima haqida bölgan, bilasizmi?'),
    ('hardware', 'Kompyuterlar nega faqat 0 va 1 bilan işlaydi, bilasizmi?'),
    ('science', 'Dark mode (qoronği rejim) közga haqiqatan foydalimi, bilasizmi?'),
]

PROMPT = """Siz IT öquv markazi (ITC Academy) öquvçilari uçun "Bilasizmi?" ruknini tayyorlovçi muharrirsiz.
{count} ta yangi savol yozing.

Talablar:
- Adabiy özbek tilida, lotin yozuvida, grammatik jihatdan benuqson.
- Mavzular (category): history — texnologiya tarixi, programming — dasturlaş, internet, security — kiberxavfsizlik,
  ai — sun'iy intellekt, hardware — texnika, science — fan, people — maşhur şaxslar. Mavzularni teng taqsimlang.
- Har bir savolning javobi bitta aniq, tekşirsa böladigan fakt bölsin (yil, ism, raqam, nom yoki sabab).
  Mavhum, umumiy yoki bahsli savollar ("qanday tadqiqotlar olib borilmoqda", "nima farqi bor") yozmang.
- Qiziqiş uyğotadigan, kam ma'lum faktlarni tanlang; jiddiy, ilmiy-ommabop ohang.
- Emoji, undov belgisi, hazil işlatmang.
- Har bir savol bitta gap, 50–150 belgi, ", bilasizmi?" bilan tugasin.
- Savollar bir-birini va quyidagi mavjud savollarni takrorlamasin.

Yaxşi namunalar:
- "Birinçi kompyuter «bug»i 1947-yilda aynan qanday haşarot bölib çiqqan, bilasizmi?" (javob: kuya)
- "Python tili nomini qaysi britaniyalik komediya şousidan olgan, bilasizmi?" (javob: Monty Python's Flying Circus)

Mavjud savollar:
{existing}

Faqat JSON qaytaring:
{{"questions": [{{"category": "<{categories}>", "text": "<savol>", "answer": "<qisqa javob, 3–10 söz>"}}]}}"""

_EMOJI_RE = re.compile('[\u200d\ufe0e\ufe0f\u20e3]')  # ZWJ, variation selector, keycap


def clean_text(text):
    """Emoji va boşqaruv belgilarini olib taşlaydi, tutuq belgilari va böşliqlarni tekislaydi."""
    text = str(text or '').replace('`', "'").replace('ʻ', "'").replace('ʼ', "'")
    text = ''.join(ch for ch in text if unicodedata.category(ch) not in ('So', 'Sk', 'Cs', 'Co', 'Cc'))
    text = re.sub(r"([oOgG])'", r'\1‘', text)    # o' g' -> o‘ g‘
    text = text.replace("'", '’')                   # qolgan tutuq: ’
    return re.sub(r'\s+', ' ', _EMOJI_RE.sub('', text)).strip()


def _valid(category, text):
    return category in CATEGORIES and 25 <= len(text) <= 220 and text.endswith('?')


def _pool():
    pool = cache.get(POOL_CACHE_KEY)
    if pool is None:
        from .models import CuriosityQuestion
        pool = list(CuriosityQuestion.objects.filter(is_active=True)
                    .values_list('category', 'text')[:POOL_SIZE])
        cache.set(POOL_CACHE_KEY, pool, 600)
    return pool or QUESTIONS


def _as_dict(category, text):
    label, icon = CATEGORIES.get(category, CATEGORIES['science'])
    return {'text': text, 'category': category, 'label': label, 'icon': icon}


def pick_question(user, now=None):
    """Foydalanuvçi uçun joriy savol: soat yoki kiriş özgarsa — boşqa savol."""
    now = now or timezone.now()
    hour = timezone.localtime(now).strftime('%Y%m%d%H')
    login = user.last_login.isoformat() if getattr(user, 'last_login', None) else ''
    digest = hashlib.sha256(f'{user.pk}|{hour}|{login}'.encode()).digest()
    pool = _pool()
    return _as_dict(*pool[int.from_bytes(digest[:4], 'big') % len(pool)])


def _client():
    api_key = (getattr(settings, 'OPENAI_API_KEY', '') or '').strip()
    if not api_key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key, timeout=60)
    except Exception:
        logger.exception('Bilasizmi: OpenAI client yaratilmadi')
        return None


def generate_batch(count=BATCH_SIZE, client=None):
    """OpenAI'dan yangi savollar olib saqlaydi. Natija: saqlangan savollar soni."""
    from .models import CuriosityQuestion
    client = client or _client()
    if client is None:
        return 0
    existing = list(CuriosityQuestion.objects.values_list('text', flat=True)[:60]) or [t for _, t in QUESTIONS]
    response = client.chat.completions.create(
        model=getattr(settings, 'CURIOSITY_OPENAI_MODEL', '') or OPENAI_MODEL,
        response_format={'type': 'json_object'},
        temperature=0.9,
        max_tokens=4000,
        messages=[{'role': 'user', 'content': PROMPT.format(
            count=count, existing='\n'.join('- ' + t for t in existing),
            categories='|'.join(CATEGORIES))}],
    )
    items = json.loads(response.choices[0].message.content or '{}').get('questions', [])
    known = {t.casefold() for t in CuriosityQuestion.objects.values_list('text', flat=True)}
    fresh = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        category, text = str(item.get('category', '')).strip().lower(), clean_text(item.get('text'))
        if _valid(category, text) and text.casefold() not in known:
            known.add(text.casefold())
            fresh.append(CuriosityQuestion(category=category, text=text))
    CuriosityQuestion.objects.bulk_create(fresh[:count], ignore_conflicts=True)
    cache.delete(POOL_CACHE_KEY)
    return len(fresh[:count])


def refresh_if_stale():
    """Oxirgi töplam eskirgan bölsa — fonda yangisini yaratadi (sahifani kutdirmaydi)."""
    if getattr(settings, 'RUNNING_TESTS', False) or not (getattr(settings, 'OPENAI_API_KEY', '') or '').strip():
        return
    if not cache.add(LOCK_KEY, 1, 3600):    # soatiga köpi bilan bir uriniş
        return
    from .models import CuriosityQuestion
    latest = CuriosityQuestion.objects.values_list('created_at', flat=True).first()
    if latest and latest > timezone.now() - timedelta(hours=REFRESH_HOURS):
        return

    def run():
        from django.db import close_old_connections
        try:
            generate_batch()
        except Exception:
            logger.exception('Bilasizmi: savollar yaratilmadi')
        finally:
            close_old_connections()

    threading.Thread(target=run, daemon=True, name='curiosity-questions').start()


def remember(request, question):
    """Şu savol AI çatda tangasiz javob olişi uçun sessiyada eslab qolinadi."""
    request.session[SESSION_KEY] = question['text']


def is_free_question(request, content):
    """Xabar aynan sahifada körsatilgan savolmi (tanga yeçilmaydi)."""
    expected = request.session.get(SESSION_KEY)
    return bool(expected) and content.strip() == expected


def consume(request):
    """Bir savol — bir tangasiz javob."""
    request.session.pop(SESSION_KEY, None)
