"""
AI-driven question generator — wraps the OpenAI chat API with strict output
validation. The caller (a DRF view) gets back the same uniform question dict
shape `quiz/importers.py` produces, so the AI preview UI and the import preview
UI can render identical previews and reuse the same commit code path.

Design choices (per user request — "AI orqali yaratishda o'ta ehtiyotkor bo'laylik"):

1. The generator NEVER touches the database. It only returns parsed,
   schema-checked questions. Commit is an explicit second call from the UI.
2. Hardcoded-3-options bug from accounts.views.generate_ai_test is fixed:
   the caller picks options_per_question (2..6).
3. JSON parsing is defensive — strips markdown code fences, retries once on
   parse failure with a stricter "JSON ONLY" reminder.
4. Every returned question is run through the same _validate_row checks
   importers.py uses, so the UI surfaces the same warning chips regardless of
   source.
5. Distractor uniqueness is enforced per-question (duplicate options are flagged).
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings

from .importers import _validate_row


SUPPORTED_TYPES = {'single_choice', 'multiple_choice', 'true_false'}
DEFAULT_MODEL = 'gpt-4o-mini'
MAX_OPTIONS = 6
MIN_OPTIONS = 2
MAX_QUESTIONS_PER_CALL = 30


# ── Public API ────────────────────────────────────────────────────────────────

def is_ai_configured() -> bool:
    """Quick check the UI can call before showing the AI button."""
    key = getattr(settings, 'OPENAI_API_KEY', None)
    return bool(key and key.strip())


def generate_questions(
    topic: str,
    *,
    count: int = 5,
    difficulty: str = 'medium',
    options_per_question: int = 4,
    question_type: str = 'single_choice',
    context: Optional[str] = None,
    language: str = 'uz',
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Ask the AI to generate `count` questions on `topic`.

    Returns `(questions, errors)`:
      * `questions` — list of dicts in importers.py shape (already validated;
        each one has its own `_errors` list).
      * `errors` — top-level errors (config missing, API failure, totally
        unparseable response). Empty list = call succeeded even if some
        individual questions have validation warnings.
    """
    topic = (topic or '').strip()
    if not topic:
        return [], ["Mavzu kiritilmagan."]

    count = max(1, min(int(count or 5), MAX_QUESTIONS_PER_CALL))
    options_per_question = max(MIN_OPTIONS, min(int(options_per_question or 4), MAX_OPTIONS))
    if question_type not in SUPPORTED_TYPES:
        question_type = 'single_choice'
    if difficulty not in ('easy', 'medium', 'hard'):
        difficulty = 'medium'

    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    if not api_key or not api_key.strip():
        return [], ["AI xizmati sozlanmagan: OPENAI_API_KEY topilmadi."]

    try:
        from openai import OpenAI
    except ImportError:
        return [], ["`openai` paket o'rnatilmagan."]

    client = OpenAI(api_key=api_key.strip(), timeout=120)
    prompt = _build_prompt(
        topic=topic, count=count, difficulty=difficulty,
        options_per_question=options_per_question,
        question_type=question_type, context=context, language=language,
    )

    ai_text, call_error = _call_openai(client, prompt)
    if call_error:
        return [], [call_error]

    raw_questions, parse_error = _parse_ai_response(ai_text)
    if parse_error:
        # one retry with stricter prompt
        retry_prompt = prompt + [{
            'role': 'user',
            'content': "Oldingi javob noto'g'ri formatda edi. FAQAT toza JSON array qaytar — markdown, izoh yoki boshqa matn YO'Q.",
        }]
        ai_text2, call_error2 = _call_openai(client, retry_prompt)
        if call_error2:
            return [], [parse_error, call_error2]
        raw_questions, parse_error = _parse_ai_response(ai_text2)
        if parse_error:
            return [], [f"AI javobini parse qilib bo'lmadi: {parse_error}"]

    questions = []
    for idx, raw in enumerate(raw_questions, start=1):
        q = _normalise_ai_question(raw, idx, question_type, difficulty)
        questions.append(q)

    return questions, []


# ── Prompt construction ───────────────────────────────────────────────────────

def _build_prompt(*, topic, count, difficulty, options_per_question,
                  question_type, context, language) -> List[Dict[str, str]]:
    type_hint = {
        'single_choice': "har bir savol uchun aynan BITTA to'g'ri javob bo'lsin",
        'multiple_choice': "har bir savol uchun KAMIDA IKKITA, ammo barchasi emas, to'g'ri javob bo'lsin",
        'true_false': "har bir savol shunchaki To'g'ri/Noto'g'ri javob talab qilsin (variantlar: 'To'g'ri' va 'Noto'g'ri')",
    }[question_type]

    difficulty_hint = {
        'easy': "boshlovchi darajadagi, sodda formulalar",
        'medium': "o'rtacha — bazaviy tushuncha + amaliy misol",
        'hard': "qiyin — chuqur tushuncha, kichik chalg'ituvchi xatolar bilan",
    }[difficulty]

    if question_type == 'true_false':
        options_per_question = 2

    schema = {
        "questions": [
            {
                "text": "Savol matni",
                "explanation": "Javobning qisqa tushuntirishi (1-2 gap)",
                "options": [
                    {"text": "Variant matni", "is_correct": True}
                    for _ in range(options_per_question)
                ],
            }
        ]
    }

    system = (
        "Sen IT/dasturlash bo'yicha tajribali ustozsan. Senga test savollari yaratish topshiriladi. "
        f"O'zbek tilida yoz. Faqat toza JSON object qaytar, boshqa hech narsa yozma.\n\n"
        f"Talablar:\n"
        f"- Aynan {count} ta savol yarat.\n"
        f"- Har bir savol uchun {options_per_question} ta javob varianti.\n"
        f"- {type_hint}.\n"
        f"- Qiyinlik darajasi: {difficulty_hint}.\n"
        f"- Variantlar bir-biridan FARQLI bo'lsin, takror matn YO'Q.\n"
        f"- Hech qachon \"yuqoridagilarning barchasi\" / \"hech qaysi\" kabi tanbal variantlar ishlatma.\n"
        f"- Har bir savol uchun qisqa (1-2 gap) izoh ber.\n"
        f"- Savol matnida AI haqida yoki o'zing haqingda gapirma; xolis va aniq formula bilan yoz.\n\n"
        "JSON sxemasi:\n"
        + json.dumps(schema, ensure_ascii=False, indent=2) + "\n\n"
        "MUHIM: Faqat JSON. Markdown ```json``` ham qo'shma."
    )

    user_lines = [f"Mavzu: {topic}"]
    if context and context.strip():
        user_lines.append(f"Qo'shimcha kontekst: {context.strip()}")
    user_lines.append(f"Shu mavzu bo'yicha {count} ta savol yarat.")

    return [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': '\n'.join(user_lines)},
    ]


# ── OpenAI call & response parsing ────────────────────────────────────────────

def _call_openai(client, messages) -> Tuple[str, Optional[str]]:
    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=messages,
            max_tokens=4000,
            temperature=0.55,
        )
        return response.choices[0].message.content or '', None
    except Exception as e:  # OpenAI's exceptions are many — catch broadly
        return '', f"AI bilan bog'lanishda xatolik: {e}"


_CODEFENCE_RE = re.compile(r'^```[a-zA-Z]*\s*|\s*```$', re.MULTILINE)


def _parse_ai_response(text: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Try hard to extract a list of question dicts from AI text."""
    if not text or not text.strip():
        return [], "AI bo'sh javob qaytardi."

    cleaned = _CODEFENCE_RE.sub('', text).strip()
    # Sometimes the model prefixes prose — find the first { or [.
    first_brace = min(
        (i for i in (cleaned.find('{'), cleaned.find('[')) if i >= 0),
        default=-1,
    )
    if first_brace > 0:
        cleaned = cleaned[first_brace:]
    # Trim trailing garbage after the matched JSON
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
        return [], "AI javobi ro'yxat ham, obyekt ham emas."

    if not isinstance(items, list):
        return [], "'questions' ro'yxat bo'lishi kerak."
    return items, None


# ── Normalisation ─────────────────────────────────────────────────────────────

def _normalise_ai_question(raw: Any, idx: int, default_type: str, difficulty: str) -> Dict[str, Any]:
    """Coerce one raw AI question into the importers.py shape + validate."""
    if not isinstance(raw, dict):
        return {
            'text': '', 'type': default_type, 'difficulty': difficulty,
            'explanation': '', 'options': [], '_row': idx,
            '_errors': [f"#{idx}-savol noto'g'ri formatda."],
        }

    text = str(raw.get('text') or raw.get('question') or '').strip()
    explanation = str(raw.get('explanation') or raw.get('izoh') or '').strip()

    options: List[Dict[str, Any]] = []
    raw_options = raw.get('options')
    if isinstance(raw_options, list):
        for o in raw_options:
            if not isinstance(o, dict):
                continue
            ot = str(o.get('text') or '').strip()
            if not ot:
                continue
            options.append({'text': ot, 'is_correct': bool(o.get('is_correct'))})
    else:
        # Fallback for the legacy A/B/C/D + correct shape some models prefer
        correct_letter = str(raw.get('correct') or '').strip().upper()
        for letter in ('A', 'B', 'C', 'D', 'E', 'F'):
            t = str(raw.get(letter.lower()) or raw.get(letter) or '').strip()
            if not t:
                continue
            options.append({'text': t, 'is_correct': letter == correct_letter})

    qtype = default_type
    correct_count = sum(1 for o in options if o['is_correct'])
    if default_type == 'single_choice' and correct_count > 1:
        qtype = 'multiple_choice'

    row = {
        'text': text,
        'type': qtype,
        'difficulty': difficulty,
        'explanation': explanation,
        'options': options,
        '_row': idx,
        '_source': 'ai',
    }
    row['_errors'] = _validate_row(row)
    return row
