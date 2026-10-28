"""
Video içidagi test (VideoQuiz) savollarini transkriptdan AI orqali yaratiş.

quiz/ai_generator.py'dan farqi: bu yerda VideoQuiz modeli talab qiladigan
A/B/C/D + bitta töğri variant (correct_option) körinişi qaytariladi.

Dizayn:
  * DB'ga heç narsa yozmaydi — faqat tekşirilgan savol luğatlarini qaytaradi.
  * JSON parse himoyalangan (markdown fence tozalaş, bir marta qayta uriniş).
  * Har bir savol validatsiyadan ötadi; yaroqsizlari taşlab yuboriladi.
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
TIMED_MAX_CHARS = 18000  # vaqt belgili transkript uçun yuqori çegara


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
    {question, option_a..d, correct_option, explanation, at_second} luğati.

    `snippets` berilsa ({'text','start','duration'} röyxati) transkript
    vaqt belgilari bilan yuboriladi va AI har bir savol uçun `at_second`
    (savol mazmuni videoda TUGAGAN soniya) qaytaradi — savol aynan öşa
    mavzu tuşuntirilganidan keyin çiqadi.
    """
    transcript = (transcript or '').strip()
    if not transcript and not snippets:
        return [], "Transkript böş."

    count = max(1, min(int(count or 5), MAX_QUESTIONS))
    if difficulty not in ('easy', 'medium', 'hard'):
        difficulty = 'medium'

    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    if not api_key or not api_key.strip():
        return [], "AI xizmati sozlanmagan (OPENAI_API_KEY topilmadi)."

    try:
        from openai import OpenAI
    except ImportError:
        return [], "`openai` paket örnatilmagan."

    timed = bool(snippets)
    if timed:
        # Vaqt belgilari matnni biroz uzaytiradi — cap'ga ozgina zaxira qöşamiz
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
            'content': "Oldingi javob notöğri formatda edi. FAQAT toza JSON obyekt qaytar.",
        }]
        text2, err2 = _call_openai(client, retry)
        if err2:
            return [], parse_err
        items, parse_err = _parse(text2)
        if parse_err:
            return [], f"AI javobini öqib bölmadi: {parse_err}"

    questions: List[Dict[str, Any]] = []
    for raw in items:
        q = _normalise(raw)
        if q is not None:
            # AI köpinça töğri javobni A ga qöyib qöyadi (position bias).
            # Prompt'dagi körsatmalarni kuçaytiriş uçun mazmunni saqlab
            # variantlarni tasodifiy joyga aralaştiramiz: correct_option ham
            # unga mos yangi harfga ötadi.
            _shuffle_options(q)
            questions.append(q)

    if not questions:
        return [], "AI heç qanday yaroqli savol qaytarmadi. Qayta urinib köring."

    return questions[:count], None


def _shuffle_options(q: Dict[str, Any]) -> None:
    """`q` luğatidagi 4 variantni tasodifiy tartiblab, correct_option'ni
    yangi joyiga mos yozadi. Joyida (in-place) işlaydi.

    Bir marta uniform shuffle: töğri javob 25% ehtimol bilan har bir harfga
    tuşadi (A, B, C, D bir xil taqsimlanadi).
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
    """Snippetlarni ~30 soniyalik bölaklarga birlaştirib [mm:ss] belgilaydi.

    Har snippetga alohida belgi qöyiş token isrofi — 30s guruhlaş
    aniqlikni saqlagan holda promptni ixçam qiladi.
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
        'easy': "boşlanğiç — sodda, töğridan-töğri faktlar",
        'medium': "örtaça — tuşunça + amaliy misol",
        'hard': "qiyin — çuqur tahlil, çalğituvçi variantlar",
    }[difficulty]

    schema_q = {
        "question": "Savol matni",
        "option_a": "A variant",
        "option_b": "B variant",
        "option_c": "C variant",
        "option_d": "D variant",
        "correct_option": "A",
        "explanation": "Nega bu javob töğri (1-2 gap)",
    }
    if timed:
        schema_q["at_second"] = 185
    schema = {"questions": [schema_q]}

    timed_rules = ""
    if timed:
        timed_rules = (
            "- Transkript [mm:ss] vaqt belgilari bilan berilgan.\n"
            "- Har bir savolga `at_second` (butun son, soniya) qöş: bu savol "
            "mazmuni videoda TÖLIQ tuşuntirib bölingan vaqt. Savol faqat "
            "`at_second` dan OLDINGI mazmunga asoslansin — öquvçi hali "
            "körmagan qismdan sörama.\n"
            "- `at_second` qiymatlari ösib borsin va savollar video böylab "
            "taqsimlansin (hammasi bir joyga töplanmasin).\n"
            "- Birinçi savol kamida 60-soniyadan keyin bölsin.\n"
        )

    system = (
        "Sen video dars asosida test tuzuvçi tajribali ustozsan. "
        "Faqat toza JSON obyekt qaytar, boşqa heç narsa yozma. Özbek tilida yoz.\n\n"
        f"Talablar:\n"
        f"- Aynan {count} ta savol yarat (agar transkript yetarli bölsa).\n"
        f"- Har bir savolda 4 ta variant (A, B, C, D) va aynan BITTA töğri javob.\n"
        f"- correct_option faqat 'A', 'B', 'C' yoki 'D' bölsin.\n"
        f"- MUHIM: töğri javobni har xil harflarga TAQSIMLA — A, B, C va D "
        f"harflari taxminan teng miqdorda bölişi kerak. Har doim A ni "
        f"tanlama! Savollar röyxatidagi correct_option qiymatlari aralaş "
        f"bölsin (masalan: B, D, A, C, B, ...).\n"
        f"- Variantlar bir-biridan farqli, takror matn yöq.\n"
        f"- 'yuqoridagilarning barçasi' kabi tanbal variantlardan foydalanma.\n"
        f"- Savollar transkript mazmuniga asoslansin.\n"
        f"{timed_rules}"
        f"- Qiyinlik: {difficulty_hint}.\n"
        f"- Har bir savol uçun qisqa izoh (explanation) ber.\n\n"
        "JSON sxemasi:\n" + json.dumps(schema, ensure_ascii=False, indent=2) + "\n\n"
        "MUHIM: Faqat JSON. Markdown ```json``` qöşma."
    )

    user_lines = ["Quyidagi video transkripti asosida test savollari tuz:\n"]
    if context and context.strip():
        user_lines.append(f"Qöşimça kontekst: {context.strip()}\n")
    user_lines.append("=== TRANSKRIPT ===")
    user_lines.append(transcript)

    return [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': '\n'.join(user_lines)},
    ]


# ── OpenAI çaqiruvi va parse ────────────────────────────────────────────────

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
        return '', f"AI bilan boğlanişda xatolik: {e}"


_CODEFENCE_RE = re.compile(r'^```[a-zA-Z]*\s*|\s*```$', re.MULTILINE)


def _parse(text: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    if not text or not text.strip():
        return [], "AI böş javob qaytardi."
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
        return [], "'questions' röyxat bölişi kerak."
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

    # Takror variant bölmasin
    lowered = [v.lower() for v in options.values()]
    if len(set(lowered)) < 4:
        return None

    correct = str(raw.get('correct_option') or '').strip().upper()[:1]
    if correct not in ('A', 'B', 'C', 'D'):
        return None

    # AI bergan vaqt belgisi (ixtiyoriy) — notöğri bölsa None qoladi,
    # view uni teng-taqsimlash fallback'iga ötkazadi.
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
# yaratuvçi generator — DB'ga tegmaydi, faqat tekşirilgan savollar qaytaradi.
