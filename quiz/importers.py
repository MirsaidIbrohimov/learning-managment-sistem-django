"""
File-based question importers — XLSX, CSV, JSON.

All parsers return the same uniform shape so the preview/commit code in
quiz/views.py treats every source identically:

    [
        {
            "text": str,                 # question text (required)
            "type": str,                 # single_choice | multiple_choice | true_false (default: single_choice)
            "difficulty": str,           # easy | medium | hard (default: medium)
            "explanation": str,          # may be empty
            "options": [{"text": str, "is_correct": bool}, ...],
            "_row": int,                 # 1-based source row (for XLSX/CSV) so the user can find errors
            "_errors": [str, ...],       # validation errors, empty list if ok
        },
        ...
    ]

The parser's job is *only* to read and shape the data plus mark obvious
per-row errors. Cross-row checks and final commit happen in the view.
"""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any, Dict, List, Tuple

from accounts.alphabet import to_new_alphabet


# ── Header aliases (flexible Uzbek/English column matching) ────────────────────

QUESTION_ALIASES = {'savol', 'savol matni', 'question', 'question_text', 'matn', 'text'}
EXPLANATION_ALIASES = {'izoh', 'tuşuntiriş', 'explanation', 'comment'}
CORRECT_ALIASES = {"töğri javob", 'togri javob', 'to gri javob', 'correct', 'correct_option', 'javob', 'answer'}
DIFFICULTY_ALIASES = {'qiyinlik', 'difficulty', 'level'}
TYPE_ALIASES = {'turi', 'tur', 'type', 'savol turi'}

DIFFICULTY_NORMALIZE = {
    'oson': 'easy', 'easy': 'easy', 'engil': 'easy',
    "örta": 'medium', 'orta': 'medium', 'medium': 'medium', 'middle': 'medium', "örtaça": 'medium',
    'qiyin': 'hard', 'hard': 'hard', 'murakkab': 'hard',
}

TYPE_NORMALIZE = {
    'single_choice': 'single_choice', 'single': 'single_choice', 'bitta': 'single_choice',
    'multiple_choice': 'multiple_choice', 'multiple': 'multiple_choice', 'multi': 'multiple_choice', "köp": 'multiple_choice',
    'true_false': 'true_false', 'tf': 'true_false', "töğri/notöğri": 'true_false',
}

OPTION_HEADER_RE = re.compile(r'^(variant\s*|option\s*|)([a-z])$', re.IGNORECASE)


def _norm(s: Any) -> str:
    """Normalise a cell header for fuzzy matching: lowercase + trim."""
    return to_new_alphabet(str(s or '').strip().lower())


def _detect_columns(headers: List[str]) -> Dict[str, Any]:
    """Map header strings to logical roles. Returns:
        {
          'question': int | None,
          'explanation': int | None,
          'correct': int | None,
          'difficulty': int | None,
          'type': int | None,
          'options': [(int, 'A'), (int, 'B'), ...],  # in column order
        }
    Header indices are 0-based.
    """
    mapping: Dict[str, Any] = {
        'question': None, 'explanation': None, 'correct': None,
        'difficulty': None, 'type': None, 'options': [],
    }
    for idx, raw in enumerate(headers):
        h = _norm(raw)
        if not h:
            continue
        if h in QUESTION_ALIASES and mapping['question'] is None:
            mapping['question'] = idx
            continue
        if h in EXPLANATION_ALIASES and mapping['explanation'] is None:
            mapping['explanation'] = idx
            continue
        if h in CORRECT_ALIASES and mapping['correct'] is None:
            mapping['correct'] = idx
            continue
        if h in DIFFICULTY_ALIASES and mapping['difficulty'] is None:
            mapping['difficulty'] = idx
            continue
        if h in TYPE_ALIASES and mapping['type'] is None:
            mapping['type'] = idx
            continue
        m = OPTION_HEADER_RE.match(h)
        if m:
            letter = m.group(2).upper()
            mapping['options'].append((idx, letter))
    # sort options by letter so A always comes before B
    mapping['options'].sort(key=lambda x: x[1])
    return mapping


def _validate_row(row: Dict[str, Any]) -> List[str]:
    """Return a list of human-readable errors for a single parsed row."""
    errors: List[str] = []
    if not row.get('text'):
        errors.append("Savol matni böş.")
    options = row.get('options') or []
    non_empty = [o for o in options if (o.get('text') or '').strip()]
    if len(non_empty) < 2:
        errors.append("Kamida 2 ta javob varianti kerak.")
    correct = [o for o in non_empty if o.get('is_correct')]
    if not correct:
        errors.append("Heç qaysi variant töğri deb belgilanmagan.")
    qtype = row.get('type', 'single_choice')
    if qtype == 'single_choice' and len(correct) > 1:
        errors.append("Bitta-tanlov uçun bittadan ortiq töğri variant belgilangan.")
    if qtype == 'multiple_choice' and len(correct) < 2 and len(non_empty) >= 2:
        # not strictly an error, but worth flagging
        errors.append("Köp-tanlov turi tanlangan, lekin faqat bitta töğri variant bor.")
    # duplicate options
    seen = set()
    for o in non_empty:
        t = (o.get('text') or '').strip().lower()
        if t in seen:
            errors.append(f"Takror variant: \"{o.get('text')}\"")
            break
        seen.add(t)
    return errors


def _row_from_tabular(values: List[Any], col_map: Dict[str, Any], row_number: int) -> Dict[str, Any]:
    """Build one normalised question dict from a tabular row + column mapping."""
    def cell(idx):
        if idx is None or idx >= len(values):
            return ''
        v = values[idx]
        return '' if v is None else str(v).strip()

    text = cell(col_map['question'])
    explanation = cell(col_map['explanation'])
    correct_letter = cell(col_map['correct']).upper()
    difficulty_raw = _norm(cell(col_map['difficulty']))
    difficulty = DIFFICULTY_NORMALIZE.get(difficulty_raw, 'medium')
    type_raw = _norm(cell(col_map['type']))
    qtype = TYPE_NORMALIZE.get(type_raw, 'single_choice')

    options = []
    correct_letters = {p.strip().upper() for p in re.split(r'[,;\s]+', correct_letter) if p.strip()}
    for col_idx, letter in col_map['options']:
        opt_text = cell(col_idx)
        if not opt_text:
            continue
        options.append({
            'text': opt_text,
            'is_correct': letter in correct_letters,
        })

    # If multiple correct letters were given but type is single_choice, upgrade to multiple_choice
    if len(correct_letters) > 1 and qtype == 'single_choice':
        qtype = 'multiple_choice'

    row = {
        'text': text,
        'type': qtype,
        'difficulty': difficulty,
        'explanation': explanation,
        'options': options,
        '_row': row_number,
    }
    row['_errors'] = _validate_row(row)
    return row


# ── XLSX ──────────────────────────────────────────────────────────────────────

def parse_xlsx(file_obj) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Parse an Excel .xlsx file. Returns (rows, top_level_errors)."""
    try:
        import openpyxl
    except ImportError:
        return [], ["openpyxl örnatilmagan."]
    try:
        wb = openpyxl.load_workbook(file_obj, data_only=True, read_only=True)
    except Exception as e:
        return [], [f"Fayl öqib bölmadi: {e}"]
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        headers_raw = next(rows_iter)
    except StopIteration:
        return [], ["Fayl böş."]
    headers = [str(h) if h is not None else '' for h in headers_raw]
    col_map = _detect_columns(headers)

    fatal = _check_column_map(col_map, headers)
    if fatal:
        return [], fatal

    rows = []
    for offset, raw in enumerate(rows_iter, start=2):
        values = list(raw)
        # skip fully empty rows
        if not any((v is not None and str(v).strip()) for v in values):
            continue
        rows.append(_row_from_tabular(values, col_map, offset))
    return rows, []


# ── CSV ───────────────────────────────────────────────────────────────────────

def parse_csv(file_obj) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Parse a CSV (UTF-8) file. Auto-detects comma/semicolon delimiter."""
    try:
        raw_bytes = file_obj.read()
        if isinstance(raw_bytes, bytes):
            try:
                text = raw_bytes.decode('utf-8-sig')
            except UnicodeDecodeError:
                text = raw_bytes.decode('cp1251', errors='replace')
        else:
            text = raw_bytes
    except Exception as e:
        return [], [f"Fayl öqib bölmadi: {e}"]

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
    except csv.Error:
        class _D(csv.excel):
            delimiter = ','
        dialect = _D

    reader = csv.reader(io.StringIO(text), dialect=dialect)
    try:
        headers = next(reader)
    except StopIteration:
        return [], ["Fayl böş."]
    col_map = _detect_columns(headers)

    fatal = _check_column_map(col_map, headers)
    if fatal:
        return [], fatal

    rows = []
    for offset, values in enumerate(reader, start=2):
        if not any(str(v).strip() for v in values):
            continue
        rows.append(_row_from_tabular(values, col_map, offset))
    return rows, []


# ── JSON ──────────────────────────────────────────────────────────────────────

def parse_json(file_obj) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Parse a JSON file. Accepted shapes:
        {"questions": [ {text, type?, difficulty?, explanation?, options: [{text, is_correct}, ...]}, ... ]}
        [{...}, {...}, ...]  (list at top level)
    """
    try:
        raw = file_obj.read()
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8-sig')
        data = json.loads(raw)
    except Exception as e:
        return [], [f"JSON xato: {e}"]

    items: List[Any]
    if isinstance(data, dict) and 'questions' in data:
        items = data['questions']
    elif isinstance(data, list):
        items = data
    else:
        return [], ["Yuqori darajada 'questions' kaliti yoki röyxat bölişi kerak."]

    if not isinstance(items, list):
        return [], ["'questions' röyxat bölişi kerak."]

    rows = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            rows.append({
                'text': '', 'type': 'single_choice', 'difficulty': 'medium',
                'explanation': '', 'options': [], '_row': idx,
                '_errors': [f"#{idx}-element dict emas."],
            })
            continue
        text = str(item.get('text') or '').strip()
        explanation = str(item.get('explanation') or '').strip()
        difficulty = DIFFICULTY_NORMALIZE.get(_norm(item.get('difficulty')), 'medium')
        qtype = TYPE_NORMALIZE.get(_norm(item.get('type')), 'single_choice')
        raw_options = item.get('options') or []
        options = []
        for o in raw_options:
            if not isinstance(o, dict):
                continue
            ot = str(o.get('text') or '').strip()
            if not ot:
                continue
            options.append({'text': ot, 'is_correct': bool(o.get('is_correct'))})

        row = {
            'text': text,
            'type': qtype,
            'difficulty': difficulty,
            'explanation': explanation,
            'options': options,
            '_row': idx,
        }
        row['_errors'] = _validate_row(row)
        rows.append(row)
    return rows, []


# ── Dispatch + helpers ────────────────────────────────────────────────────────

def _check_column_map(col_map: Dict[str, Any], headers: List[str]) -> List[str]:
    """Top-level errors that make per-row parsing pointless."""
    missing = []
    if col_map['question'] is None:
        missing.append("'Savol' (yoki 'Question') ustuni")
    if col_map['correct'] is None:
        missing.append("'Töğri javob' (yoki 'Correct') ustuni")
    if len(col_map['options']) < 2:
        missing.append("Kamida 2 ta variant ustuni (Variant A, Variant B)")
    if missing:
        detected = ', '.join(repr(h) for h in headers if h)
        return [
            "Quyidagi majburiy ustun(lar) topilmadi: " + '; '.join(missing) + '.',
            f"Topilgan ustunlar: {detected or '(bo''sh)'}.",
            "Iltimos, namuna fayldagi sarlavhalar bilan soliştirib köring.",
        ]
    return []


def parse_file(file_obj, filename: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Dispatch to the right parser based on file extension."""
    name = (filename or '').lower()
    if name.endswith('.xlsx'):
        return parse_xlsx(file_obj)
    if name.endswith('.csv'):
        return parse_csv(file_obj)
    if name.endswith('.json'):
        return parse_json(file_obj)
    return [], [f"Format qöllab-quvvatlanmaydi: .xlsx, .csv yoki .json yuklang."]
