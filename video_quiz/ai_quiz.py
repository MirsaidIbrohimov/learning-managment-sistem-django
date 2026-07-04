"""
Video ichidagi test (VideoQuiz) savollarini transkriptdan AI orqali yaratish.

quiz/ai_generator.py'dan farqi: bu yerda VideoQuiz modeli talab qiladigan
A/B/C/D + bitta to'g'ri variant (correct_option) ko'rinishi qaytariladi.

Dizayn:
  * DB'ga hech narsa yozmaydi — faqat tekshirilgan savol lug'atlarini qaytaradi.
  * JSON parse himoyalangan (markdown fence tozalash, bir marta qayta urinish).
  * Har bir savol validatsiyadan o'tadi; yaroqsizlari tashlab yuboriladi.
"""
from __future__ import annotations

import json
import random
import re
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings

DEFAULT_MODEL = 'gpt-4o-mini'
MAX_QUESTIONS = 20
MIN_QUESTION_LEN = 5
TIMED_MAX_CHARS = 18000  # vaqt belgili transkript uchun yuqori chegara


def is_ai_configured() -> bool:
    key = getattr(settings, 'OPENAI_API_KEY', None)
    return bool(key and key.strip())


def generate_video_quizzes(
    transcript: str,
    *,
    count: int = 5,
    difficulty: str = 'medium',
    context: Optional[str] = None,
    language: str = 'uz',
    snippets: Optional[List[dict]] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Transkript matnidan `count` ta video test savoli yaratadi.

    (questions, error) qaytaradi. `questions` — har biri
    {question, option_a..d, correct_option, explanation, at_second} lug'ati.

    `snippets` berilsa ({'text','start','duration'} ro'yxati) transkript
    vaqt belgilari bilan yuboriladi va AI har bir savol uchun `at_second`
    (savol mazmuni videoda TUGAGAN soniya) qaytaradi — savol aynan o'sha
    mavzu tushuntirilganidan keyin chiqadi.
    """
    transcript = (transcript or '').strip()
    if not transcript and not snippets:
        return [], "Transkript bo'sh."

    count = max(1, min(int(count or 5), MAX_QUESTIONS))
    if difficulty not in ('easy', 'medium', 'hard'):
        difficulty = 'medium'

    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    if not api_key or not api_key.strip():
        return [], "AI xizmati sozlanmagan (OPENAI_API_KEY topilmadi)."

    try:
        from openai import OpenAI
    except ImportError:
        return [], "`openai` paket o'rnatilmagan."

    timed = bool(snippets)
    if timed:
        # Vaqt belgilari matnni biroz uzaytiradi — cap'ga ozgina zaxira qo'shamiz
        transcript = _format_timed_transcript(snippets, max_chars=TIMED_MAX_CHARS)

    client = OpenAI(api_key=api_key.strip(), timeout=120)
    messages = _build_prompt(transcript, count, difficulty, context, timed=timed)

    text, err = _call_openai(client, messages)
    if err:
        return [], err

    items, parse_err = _parse(text)
    if parse_err:
        retry = messages + [{
            'role': 'user',
            'content': "Oldingi javob noto'g'ri formatda edi. FAQAT toza JSON obyekt qaytar.",
        }]
        text2, err2 = _call_openai(client, retry)
        if err2:
            return [], parse_err
        items, parse_err = _parse(text2)
        if parse_err:
            return [], f"AI javobini o'qib bo'lmadi: {parse_err}"

    questions: List[Dict[str, Any]] = []
    for raw in items:
        q = _normalise(raw)
        if q is not None:
            # AI ko'pincha to'g'ri javobni A ga qo'yib qo'yadi (position bias).
            # Prompt'dagi ko'rsatmalarni kuchaytirish uchun mazmunni saqlab
            # variantlarni tasodifiy joyga aralashtiramiz: correct_option ham
            # unga mos yangi harfga o'tadi.
            _shuffle_options(q)
            questions.append(q)

    if not questions:
        return [], "AI hech qanday yaroqli savol qaytarmadi. Qayta urinib ko'ring."

    return questions[:count], None


def _shuffle_options(q: Dict[str, Any]) -> None:
    """`q` lug'atidagi 4 variantni tasodifiy tartiblab, correct_option'ni
    yangi joyiga mos yozadi. Joyida (in-place) ishlaydi.

    Bir marta uniform shuffle: to'g'ri javob 25% ehtimol bilan har bir harfga
    tushadi (A, B, C, D bir xil taqsimlanadi).
    """
    letters = ['A', 'B', 'C', 'D']
    values = [q['option_a'], q['option_b'], q['option_c'], q['option_d']]
    correct_val = values[letters.index(q['correct_option'])]

    order = list(range(4))
    random.shuffle(order)
    new_values = [values[i] for i in order]

    q['option_a'], q['option_b'], q['option_c'], q['option_d'] = new_values
    q['correct_option'] = letters[new_values.index(correct_val)]


# ── Vaqt belgili transkript ──────────────────────────────────────────────────

def _format_timed_transcript(snippets: List[dict], *, max_chars: int = 16000) -> str:
    """Snippetlarni ~30 soniyalik bo'laklarga birlashtirib [mm:ss] belgilaydi.

    Har snippetga alohida belgi qo'yish token isrofi — 30s guruhlash
    aniqlikni saqlagan holda promptni ixcham qiladi.
    """
    CHUNK_SEC = 30
    lines: List[str] = []
    bucket_start = None
    bucket_texts: List[str] = []

    def flush():
        if bucket_start is None or not bucket_texts:
            return
        m, s = divmod(int(bucket_start), 60)
        lines.append(f"[{m:02d}:{s:02d}] " + ' '.join(bucket_texts))

    for sn in snippets:
        try:
            start = float(sn.get('start', 0) or 0)
        except (TypeError, ValueError):
            start = 0.0
        text = (sn.get('text') or '').strip()
        if not text:
            continue
        if bucket_start is None:
            bucket_start = start
        if start - bucket_start >= CHUNK_SEC:
            flush()
            bucket_start = start
            bucket_texts = []
        bucket_texts.append(text)
    flush()

    result = '\n'.join(lines)
    return result[:max_chars] if len(result) > max_chars else result


# ── Prompt ──────────────────────────────────────────────────────────────────

def _build_prompt(transcript, count, difficulty, context, *, timed=False) -> List[Dict[str, str]]:
    difficulty_hint = {
        'easy': "boshlang'ich — sodda, to'g'ridan-to'g'ri faktlar",
        'medium': "o'rtacha — tushuncha + amaliy misol",
        'hard': "qiyin — chuqur tahlil, chalg'ituvchi variantlar",
    }[difficulty]

    schema_q = {
        "question": "Savol matni",
        "option_a": "A variant",
        "option_b": "B variant",
        "option_c": "C variant",
        "option_d": "D variant",
        "correct_option": "A",
        "explanation": "Nega bu javob to'g'ri (1-2 gap)",
    }
    if timed:
        schema_q["at_second"] = 185
    schema = {"questions": [schema_q]}

    timed_rules = ""
    if timed:
        timed_rules = (
            "- Transkript [mm:ss] vaqt belgilari bilan berilgan.\n"
            "- Har bir savolga `at_second` (butun son, soniya) qo'sh: bu savol "
            "mazmuni videoda TO'LIQ tushuntirib bo'lingan vaqt. Savol faqat "
            "`at_second` dan OLDINGI mazmunga asoslansin — o'quvchi hali "
            "ko'rmagan qismdan so'rama.\n"
            "- `at_second` qiymatlari o'sib borsin va savollar video bo'ylab "
            "taqsimlansin (hammasi bir joyga to'planmasin).\n"
            "- Birinchi savol kamida 60-soniyadan keyin bo'lsin.\n"
        )

    system = (
        "Sen video dars asosida test tuzuvchi tajribali ustozsan. "
        "Faqat toza JSON obyekt qaytar, boshqa hech narsa yozma. O'zbek tilida yoz.\n\n"
        f"Talablar:\n"
        f"- Aynan {count} ta savol yarat (agar transkript yetarli bo'lsa).\n"
        f"- Har bir savolda 4 ta variant (A, B, C, D) va aynan BITTA to'g'ri javob.\n"
        f"- correct_option faqat 'A', 'B', 'C' yoki 'D' bo'lsin.\n"
        f"- MUHIM: to'g'ri javobni har xil harflarga TAQSIMLA — A, B, C va D "
        f"harflari taxminan teng miqdorda bo'lishi kerak. Har doim A ni "
        f"tanlama! Savollar ro'yxatidagi correct_option qiymatlari aralash "
        f"bo'lsin (masalan: B, D, A, C, B, ...).\n"
        f"- Variantlar bir-biridan farqli, takror matn yo'q.\n"
        f"- 'yuqoridagilarning barchasi' kabi tanbal variantlardan foydalanma.\n"
        f"- Savollar transkript mazmuniga asoslansin.\n"
        f"{timed_rules}"
        f"- Qiyinlik: {difficulty_hint}.\n"
        f"- Har bir savol uchun qisqa izoh (explanation) ber.\n\n"
        "JSON sxemasi:\n" + json.dumps(schema, ensure_ascii=False, indent=2) + "\n\n"
        "MUHIM: Faqat JSON. Markdown ```json``` qo'shma."
    )

    user_lines = ["Quyidagi video transkripti asosida test savollari tuz:\n"]
    if context and context.strip():
        user_lines.append(f"Qo'shimcha kontekst: {context.strip()}\n")
    user_lines.append("=== TRANSKRIPT ===")
    user_lines.append(transcript)

    return [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': '\n'.join(user_lines)},
    ]


# ── OpenAI chaqiruvi va parse ────────────────────────────────────────────────

def _call_openai(client, messages) -> Tuple[str, Optional[str]]:
    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=messages,
            max_tokens=4000,
            temperature=0.5,
        )
        return response.choices[0].message.content or '', None
    except Exception as e:
        return '', f"AI bilan bog'lanishda xatolik: {e}"


_CODEFENCE_RE = re.compile(r'^```[a-zA-Z]*\s*|\s*```$', re.MULTILINE)


def _parse(text: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    if not text or not text.strip():
        return [], "AI bo'sh javob qaytardi."
    cleaned = _CODEFENCE_RE.sub('', text).strip()
    first = min((i for i in (cleaned.find('{'), cleaned.find('[')) if i >= 0), default=-1)
    if first > 0:
        cleaned = cleaned[first:]
    cleaned = cleaned.rstrip(' \n\t\r,;')
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return [], f"JSON sintaksi xato: {e}"

    if isinstance(data, dict):
        items = data.get('questions') or data.get('items') or []
    elif isinstance(data, list):
        items = data
    else:
        return [], "AI javobi kutilgan formatda emas."
    if not isinstance(items, list):
        return [], "'questions' ro'yxat bo'lishi kerak."
    return items, None


# ── Normalizatsiya + validatsiya ─────────────────────────────────────────────

def _normalise(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None

    question = str(raw.get('question') or raw.get('text') or '').strip()
    if len(question) < MIN_QUESTION_LEN:
        return None

    options = {}
    for key in ('a', 'b', 'c', 'd'):
        val = str(raw.get(f'option_{key}') or '').strip()
        if not val:
            return None
        options[key] = val[:300]

    # Takror variant bo'lmasin
    lowered = [v.lower() for v in options.values()]
    if len(set(lowered)) < 4:
        return None

    correct = str(raw.get('correct_option') or '').strip().upper()[:1]
    if correct not in ('A', 'B', 'C', 'D'):
        return None

    # AI bergan vaqt belgisi (ixtiyoriy) — noto'g'ri bo'lsa None qoladi,
    # view uni teng-taqsimlash fallback'iga o'tkazadi.
    at_second = None
    try:
        raw_at = raw.get('at_second')
        if raw_at is not None:
            at_second = max(0, int(float(raw_at)))
    except (TypeError, ValueError):
        at_second = None

    return {
        'question': question[:2000],
        'option_a': options['a'],
        'option_b': options['b'],
        'option_c': options['c'],
        'option_d': options['d'],
        'correct_option': correct,
        'explanation': str(raw.get('explanation') or '').strip()[:2000],
        'at_second': at_second,
    }


# Bu fayl: video transkriptidan VideoQuiz (A/B/C/D) savollarini AI orqali
# yaratuvchi generator — DB'ga tegmaydi, faqat tekshirilgan savollar qaytaradi.
