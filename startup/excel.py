"""Startuplar uchun Excel eksport / import.

Nega alohida modul: repo'da bu kod har joyda view ichida takrorlangan
(`accounts/views.py:_generate_students_excel`, `games/views.py`,
`quiz/importers.py`). Bu yerda HTTP bilan ishlash yo'q — view faqat
`build_export_workbook()` / `parse_import_file()` natijasini uzatadi,
shuning uchun testlash oson.

Xavfsizlik: eksportda ham, importda ham maydonlar **oq roʻyxat** orqali
oʻtadi; foydalanuvchi bergan ustun nomi hech qachon toʻgʻridan-toʻgʻri
modelga yozilmaydi.
"""

from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from .models import (
    CATEGORY_CHOICES,
    PitchDeck,
    Startup,
    StartupFinance,
    StartupMember,
    StartupMentor,
    StartupTask,
)

MAX_IMPORT_ROWS = 500
MAX_IMPORT_SIZE = 5 * 1024 * 1024

HEADER_FILL = '667eea'

# ─────────────────────────── Eksport ───────────────────────────

EXPORT_FIELDS = {
    'name': 'Startup nomi',
    'owner_username': 'Egasi (username)',
    'owner_full_name': 'Egasi (F.I.Sh)',
    'owner_phone': 'Egasi telefoni',
    'category': 'Kategoriya',
    'profession': 'Kurs / kasb',
    'short_description': 'Qisqa tavsif',
    'description': 'Toʻliq tavsif',
    'problem': 'Muammo',
    'solution': 'Yechim',
    'target_audience': 'Maqsadli auditoriya',
    'business_model': 'Biznes model',
    'competitors': 'Raqobatchilar',
    'current_stage': 'Joriy bosqich',
    'progress': 'Progress (%)',
    'status': 'Holat',
    'total_xp': 'Umumiy XP',
    'member_count': 'Jamoa aʻzolari',
    'task_total': 'Vazifalar (jami)',
    'task_completed': 'Vazifalar (bajarilgan)',
    'mentors': 'Mentorlar',
    'revenue': 'Daromad',
    'expense': 'Xarajat',
    'profit': 'Foyda',
    'pitch_filled': 'Pitch deck (10 dan)',
    'website': 'Sayt',
    'github_url': 'GitHub',
    'telegram_url': 'Telegram',
    'instagram_url': 'Instagram',
    'created_at': 'Yaratilgan',
    'updated_at': 'Yangilangan',
}

DEFAULT_EXPORT_FIELDS = [
    'name', 'owner_username', 'owner_full_name', 'category', 'profession',
    'short_description', 'problem', 'solution', 'current_stage', 'progress',
    'status', 'total_xp', 'member_count', 'task_completed', 'created_at',
]


def _related_maps(startup_ids):
    """Bitta so'rovda barcha bogʻliq sanoqlar — N+1 va Sum/Count join
    aralashib ketishidan qochish uchun har biri alohida guruhlanadi."""
    tasks = {}
    for row in (StartupTask.objects.filter(startup_id__in=startup_ids)
                .values('startup_id', 'status').annotate(total=Count('id'))):
        tasks.setdefault(row['startup_id'], {})[row['status']] = row['total']

    members = {
        row['startup_id']: row['total']
        for row in (StartupMember.objects
                    .filter(startup_id__in=startup_ids, status='active')
                    .values('startup_id').annotate(total=Count('id')))
    }

    finance = {}
    for row in (StartupFinance.objects.filter(startup_id__in=startup_ids)
                .values('startup_id', 'type').annotate(total=Sum('amount'))):
        finance.setdefault(row['startup_id'], {})[row['type']] = row['total']

    mentors = {}
    for link in (StartupMentor.objects
                 .filter(startup_id__in=startup_ids, is_active=True)
                 .select_related('mentor')):
        name = link.mentor.get_full_name() or link.mentor.username
        mentors.setdefault(link.startup_id, []).append(name)

    pitch = {
        deck.startup_id: deck.filled_count
        for deck in PitchDeck.objects.filter(startup_id__in=startup_ids)
    }
    return {'tasks': tasks, 'members': members, 'finance': finance,
            'mentors': mentors, 'pitch': pitch}


def _cell_value(startup, field, maps):
    tasks = maps['tasks'].get(startup.pk, {})
    finance = maps['finance'].get(startup.pk, {})
    revenue = finance.get('REVENUE') or Decimal('0')
    expense = finance.get('EXPENSE') or Decimal('0')

    if field == 'name':
        return startup.name
    if field == 'owner_username':
        return startup.owner.username
    if field == 'owner_full_name':
        return startup.owner.get_full_name() or startup.owner.username
    if field == 'owner_phone':
        return getattr(startup.owner, 'phone', '') or ''
    if field == 'category':
        return startup.get_category_display()
    if field == 'profession':
        return startup.profession.name if startup.profession else ''
    if field == 'current_stage':
        return startup.current_stage_label
    if field == 'status':
        return startup.get_status_display()
    if field == 'member_count':
        return maps['members'].get(startup.pk, 0)
    if field == 'task_total':
        return sum(tasks.values())
    if field == 'task_completed':
        return tasks.get('COMPLETED', 0)
    if field == 'mentors':
        return ', '.join(maps['mentors'].get(startup.pk, []))
    if field == 'revenue':
        return revenue
    if field == 'expense':
        return expense
    if field == 'profit':
        return revenue - expense
    if field == 'pitch_filled':
        return maps['pitch'].get(startup.pk, 0)
    if field in ('created_at', 'updated_at'):
        value = getattr(startup, field)
        # openpyxl timezone-aware datetime yozolmaydi — matn sifatida beramiz.
        return timezone.localtime(value).strftime('%d.%m.%Y %H:%M') if value else ''
    return getattr(startup, field, '')


def build_export_workbook(queryset, selected_fields):
    """Tanlangan maydonlar boʻyicha `openpyxl.Workbook` qaytaradi."""
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    fields = [f for f in selected_fields if f in EXPORT_FIELDS] or list(DEFAULT_EXPORT_FIELDS)

    startups = list(queryset.select_related('owner', 'profession'))
    maps = _related_maps([s.pk for s in startups])

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = 'Startuplar'

    header_font = Font(name='Arial', bold=True, size=12, color='FFFFFF')
    header_fill = PatternFill(start_color=HEADER_FILL, end_color=HEADER_FILL,
                              fill_type='solid')
    header_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
    cell_align = Alignment(vertical='top', wrap_text=True)
    thin = Side(style='thin')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for index, field in enumerate(fields, start=1):
        cell = sheet.cell(row=1, column=index, value=EXPORT_FIELDS[field])
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = border

    for row_index, startup in enumerate(startups, start=2):
        for col_index, field in enumerate(fields, start=1):
            cell = sheet.cell(row=row_index, column=col_index,
                              value=_cell_value(startup, field, maps))
            cell.alignment = cell_align
            cell.border = border

    for index, field in enumerate(fields, start=1):
        width = 42 if field in ('description', 'problem', 'solution',
                                'target_audience', 'business_model',
                                'competitors', 'short_description') else 20
        sheet.column_dimensions[get_column_letter(index)].width = width

    sheet.freeze_panes = 'A2'
    return workbook


# ─────────────────────────── Import ───────────────────────────

# Ustun → qabul qilinadigan sarlavhalar. Eksport fayli toʻgʻridan-toʻgʻri
# qaytib import qilinishi uchun oʻzbekcha sarlavhalar ham roʻyxatda.
IMPORT_COLUMNS = {
    'owner_username': ['owner_username', 'Egasi (username)', 'username', 'Egasi'],
    'name': ['name', 'Startup nomi', 'nomi'],
    'short_description': ['short_description', 'Qisqa tavsif'],
    'description': ['description', 'Toʻliq tavsif', "To'liq tavsif"],
    'problem': ['problem', 'Muammo'],
    'solution': ['solution', 'Yechim'],
    'target_audience': ['target_audience', 'Maqsadli auditoriya'],
    'business_model': ['business_model', 'Biznes model'],
    'competitors': ['competitors', 'Raqobatchilar'],
    'category': ['category', 'Kategoriya'],
    'profession': ['profession', 'Kurs / kasb', 'Kurs', 'Kasb'],
    'website': ['website', 'Sayt'],
    'github_url': ['github_url', 'GitHub'],
    'telegram_url': ['telegram_url', 'Telegram'],
    'instagram_url': ['instagram_url', 'Instagram'],
    'status': ['status', 'Holat'],
}

REQUIRED_COLUMNS = ['owner_username', 'name', 'short_description']

# Import qilinmaydigan (hisoblanadigan) maydonlar — hujjat uchun.
DERIVED_FIELDS = ['slug', 'progress', 'current_stage', 'total_xp', 'logo', 'created_at']


def _norm(value):
    """Sarlavhani solishtirish uchun: faqat harf/raqam, kichik harfda."""
    if value is None:
        return ''
    return ''.join(ch for ch in str(value).lower() if ch.isalnum())


_CATEGORY_LOOKUP = {}
for _code, _label in CATEGORY_CHOICES:
    _CATEGORY_LOOKUP[_norm(_code)] = _code
    _CATEGORY_LOOKUP[_norm(_label)] = _code

_STATUS_LOOKUP = {}
for _code, _label in Startup.STATUS_CHOICES:
    _STATUS_LOOKUP[_norm(_code)] = _code
    _STATUS_LOOKUP[_norm(_label)] = _code


def resolve_category(value):
    return _CATEGORY_LOOKUP.get(_norm(value), 'Other')


def resolve_status(value):
    return _STATUS_LOOKUP.get(_norm(value))


def detect_columns(headers):
    """Sarlavha qatoridan {ustun kaliti: indeks} lugʻatini yasaydi."""
    normalized = {_norm(header): index for index, header in enumerate(headers)}
    mapping = {}
    for key, aliases in IMPORT_COLUMNS.items():
        for alias in aliases:
            index = normalized.get(_norm(alias))
            if index is not None:
                mapping[key] = index
                break
    return mapping


def parse_import_file(file_obj):
    """`.xlsx` faylni qatorlarga ajratadi.

    Qaytaradi `(rows, errors)`: `rows` — har biri `{'row': int, 'data': {...}}`,
    `errors` — faylning oʻzi bilan bogʻliq halokatli xatolar roʻyxati.
    """
    try:
        import openpyxl
    except ImportError:
        return [], ["openpyxl kutubxonasi oʻrnatilmagan. pip install openpyxl"]

    try:
        workbook = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)
        sheet = workbook.active
    except Exception:
        return [], ["Faylni oʻqib boʻlmadi. Toʻgʻri .xlsx fayl ekanini tekshiring."]

    rows_iter = sheet.iter_rows(values_only=True)
    try:
        headers = next(rows_iter)
    except StopIteration:
        return [], ['Fayl boʻsh.']

    columns = detect_columns(list(headers))
    missing = [IMPORT_COLUMNS[key][1] for key in REQUIRED_COLUMNS if key not in columns]
    if missing:
        return [], [f"Majburiy ustunlar topilmadi: {', '.join(missing)}"]

    rows = []
    errors = []
    for number, raw in enumerate(rows_iter, start=2):
        values = list(raw)
        if not any(value is not None and str(value).strip() for value in values):
            continue

        data = {}
        for key, index in columns.items():
            value = values[index] if index < len(values) else None
            data[key] = str(value).strip() if value is not None else ''
        rows.append({'row': number, 'data': data})

        if len(rows) >= MAX_IMPORT_ROWS:
            errors.append(f'Limit: bir importda maksimal {MAX_IMPORT_ROWS} qator '
                          f'qabul qilinadi — qolgan qatorlar oʻqilmadi.')
            break

    workbook.close()
    if not rows:
        errors.append('Faylda import qilinadigan qator topilmadi.')
    return rows, errors


def build_import_template():
    """Namuna `.xlsx`: sarlavhalar, misol qator va dropdown'lar."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = 'Startuplar'

    keys = list(IMPORT_COLUMNS.keys())
    headers = [IMPORT_COLUMNS[key][1] for key in keys]
    example = {
        'owner_username': 'oquvchi_username',
        'name': 'SmartAgro',
        'short_description': 'Fermerlar uchun aqlli suv nazorati',
        'problem': 'Suv isrof boʻladi',
        'solution': 'IoT sensor + mobil ilova',
        'category': 'AgriTech',
        'status': 'Faol',
    }

    header_font = Font(name='Arial', bold=True, size=12, color='FFFFFF')
    header_fill = PatternFill(start_color=HEADER_FILL, end_color=HEADER_FILL,
                              fill_type='solid')

    for index, (key, header) in enumerate(zip(keys, headers), start=1):
        cell = sheet.cell(row=1, column=index, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        sheet.cell(row=2, column=index, value=example.get(key, ''))
        sheet.column_dimensions[get_column_letter(index)].width = 26

    def _dropdown(key, options):
        if key not in keys:
            return
        letter = get_column_letter(keys.index(key) + 1)
        validation = DataValidation(type='list',
                                    formula1=f'"{",".join(options)}"',
                                    allow_blank=True)
        sheet.add_data_validation(validation)
        validation.add(f'{letter}2:{letter}501')

    _dropdown('category', [label for _, label in CATEGORY_CHOICES])
    _dropdown('status', [label for _, label in Startup.STATUS_CHOICES])

    notes = workbook.create_sheet('Yordam')
    notes['A1'] = 'Import qoidalari'
    notes['A1'].font = Font(bold=True, size=13)
    for index, line in enumerate([
        'Majburiy ustunlar: Egasi (username), Startup nomi, Qisqa tavsif.',
        'Egasi — LMS dagi mavjud oʻquvchi username i boʻlishi shart.',
        '"Yaratish" rejimida oʻquvchida faol startup boʻlsa qator oʻtkazib yuboriladi.',
        '"Yangilash" rejimida oʻquvchining faol startupi maydonlari yangilanadi.',
        f"Hisoblanadigan maydonlar import qilinmaydi: {', '.join(DERIVED_FIELDS)}.",
        f'Bir faylda maksimal {MAX_IMPORT_ROWS} qator, fayl hajmi 5 MB gacha.',
        'Bosqich va progress vazifalar bajarilishiga qarab avtomatik hisoblanadi.',
    ], start=3):
        notes[f'A{index}'] = line
    notes.column_dimensions['A'].width = 96

    return workbook
