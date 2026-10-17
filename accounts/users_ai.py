"""AI Foydalanuvchi Boshqaruvchisi — admin paneldagi "Foydalanuvchilar"
sahifasi uchun sun'iy intellekt yordamchisi.

Ikki rejimda ishlaydi:

1. **OpenAI agent rejimi** (OPENAI_API_KEY sozlangan bo'lsa):
   GPT modeli function-calling orqali quyidagi vositalarni o'zi tanlab
   chaqiradi: foydalanuvchi qidirish, to'liq profil o'qish, statistika,
   ro'yxatlar (rol/status/guruh bo'yicha) hamda HARAKATLAR — bloklash,
   blokdan chiqarish, kursni tugatgan deb belgilash, ism-familiyani
   tuzatish, barcha ismlarni bosh harfini katta qilish, o'chirish.
   Javob o'zbek tilida, profil havolalari (markdown) bilan qaytariladi.

2. **Offline fallback rejimi** (API kalit yo'q bo'lsa):
   Eng ko'p so'raladigan savol/buyruqlarni oddiy qoidalar asosida
   bajaradi (statistika, bloklanganlar ro'yxati, bloklash/blokdan
   chiqarish, ismlarni katta harf qilish, foydalanuvchi qidirish).

Xavfsizlik qoidalari:
- Admin va superuser hisoblariga nisbatan har qanday o'zgartirish
  (bloklash/o'chirish) RAD ETILADI.
- O'chirish faqat admin aniq "o'chir" deb yozganda bajariladi.
- Barcha bajarilgan harakatlar javobda hisobot qilib ko'rsatiladi.
"""
import json
import re
from datetime import timedelta

from django.conf import settings
from django.db.models import Q, Count
from django.urls import reverse
from django.utils import timezone

# ---------------------------------------------------------------------------
#  Konfiguratsiya
# ---------------------------------------------------------------------------
AI_MODEL = "gpt-4o-mini"
AI_MAX_TOKENS = 1600
AI_TEMPERATURE = 0.2
AGENT_MAX_STEPS = 8          # harakatli buyruqlar ko'proq qadam talab qilishi mumkin
MAX_LIST_RESULTS = 30        # ro'yxat tool'laridagi maksimal natija
MAX_BULK_UPDATES = 3000      # bulk ism tuzatishdagi maksimal yangilash

_PROTECTED_ROLES = ('admin',)
_ONLINE_WINDOW = timedelta(minutes=5)

_ROLE_LABELS = {
    'student': "O'quvchi",
    'teacher': "O'qituvchi",
    'admin': 'Admin',
    'assistant_admin': 'Yordamchi admin',
}


# ---------------------------------------------------------------------------
#  Umumiy yordamchilar
# ---------------------------------------------------------------------------
def _user_model():
    from .models import CustomUser
    return CustomUser


def _role_label(user):
    return _ROLE_LABELS.get(user.role, user.role)


def _user_name(user):
    return (user.full_name or '').strip() or user.username


def _user_url(pk):
    try:
        return reverse('admin_user_view', args=[int(pk)])
    except Exception:
        return None


def _user_link(user):
    url = _user_url(user.pk)
    if not url:
        return None
    return {'url': url, 'label': _user_name(user)}


def _is_protected(user):
    return user.role in _PROTECTED_ROLES or user.is_superuser


def _short(user_dict_list):
    return user_dict_list


def _user_row(u, status=None, extra=None):
    row = {
        'user_id': u.pk,
        'name': _user_name(u),
        'username': u.username,
        'role': _role_label(u),
        'blocked': bool(u.is_blocked),
    }
    if getattr(u, 'phone', None):
        row['phone'] = u.phone
    if getattr(u, 'student_id', None):
        row['student_id'] = u.student_id
    if status is not None:
        row['blocked'] = bool(status)
    if extra:
        row.update(extra)
    return row


def _find_users(query, limit=6):
    """Ism/familiya/username/telefon/ID bo'yicha foydalanuvchi qidirish."""
    CustomUser = _user_model()
    query = (query or '').strip()
    if not query:
        return []
    q = Q()
    for token in query.split():
        if len(token) < 2:
            continue
        q |= (Q(first_name__icontains=token) | Q(last_name__icontains=token)
              | Q(username__icontains=token) | Q(phone__icontains=token))
    if query.isdigit():
        q |= Q(student_id=int(query))
    if not q:
        return []
    return list(
        CustomUser.objects.filter(q)
        .order_by('first_name', 'last_name')[:limit]
    )


def _apply_list_filters(qs, role=None, status=None, group_id=None, online=None):
    if role:
        qs = qs.filter(role=role)
    if status == 'blocked':
        qs = qs.filter(is_blocked=True)
    elif status == 'active':
        qs = qs.filter(is_blocked=False)
    if group_id:
        qs = qs.filter(study_groups__id=group_id).distinct()
    if online:
        qs = qs.filter(last_activity__gte=timezone.now() - _ONLINE_WINDOW)
    return qs


# ---------------------------------------------------------------------------
#  TOOL implementatsiyalari — har biri (json_matn, havolalar) qaytaradi
# ---------------------------------------------------------------------------
def tool_search_users(query, role=None, limit=8):
    """Foydalanuvcharni ism/username/telefon/ID bo'yicha qidirish."""
    users = _find_users(query, limit=min(int(limit or 8), MAX_LIST_RESULTS))
    if not users:
        return json.dumps({'found': [], 'note': 'Bunday foydalanuvchi topilmadi.'},
                          ensure_ascii=False), []
    rows, links = [], []
    for u in users:
        if role and u.role != role:
            continue
        rows.append(_user_row(u, extra={'profile_url': _user_url(u.pk)}))
        lnk = _user_link(u)
        if lnk:
            links.append(lnk)
    return json.dumps({'found': rows}, ensure_ascii=False), links


def tool_get_user_profile(user_id):
    """Foydalanuvchining to'liq profili — barcha asosiy ma'lumotlar."""
    CustomUser = _user_model()
    try:
        u = CustomUser.objects.select_related('profession').get(pk=int(user_id))
    except (CustomUser.DoesNotExist, ValueError, TypeError):
        return json.dumps({'error': 'Foydalanuvchi topilmadi.'}, ensure_ascii=False), []

    groups = [g.name for g in u.study_groups.all()[:6]]
    contract = False
    try:
        from .models import StudentBalance
        contract = StudentBalance.objects.filter(user_id=u.pk, is_contract=True).exists()
    except Exception:
        pass

    profile = {
        'user_id': u.pk,
        'name': _user_name(u),
        'first_name': u.first_name,
        'last_name': u.last_name,
        'username': u.username,
        'student_id': u.student_id,
        'phone': u.phone,
        'email': u.email or None,
        'role': _role_label(u),
        'blocked': bool(u.is_blocked),
        'finished_course': bool(u.is_finished),
        'premium': bool(u.is_premium),
        'coins': getattr(u, 'coins', 0),
        'telegram': u.telegram_username or (str(u.telegram_id) if u.telegram_id else None),
        'profession': u.profession.name if u.profession else None,
        'groups': groups,
        'contract': contract,
        'birth_date': u.birth_date.strftime('%d.%m.%Y') if u.birth_date else None,
        'gender': u.gender or None,
        'address': u.address or None,
        'joined_at': timezone.localtime(u.date_joined).strftime('%d.%m.%Y %H:%M'),
        'last_activity': (timezone.localtime(u.last_activity).strftime('%d.%m.%Y %H:%M')
                          if u.last_activity else None),
        'online_now': bool(u.is_online),
        'profile_url': _user_url(u.pk),
    }
    lnk = _user_link(u)
    return json.dumps({'profile': profile}, ensure_ascii=False), ([lnk] if lnk else [])


def tool_get_user_stats():
    """Butun tizimdagi foydalanuvchilar statistikasi."""
    CustomUser = _user_model()
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    agg = CustomUser.objects.aggregate(
        total=Count('id'),
        students=Count('id', filter=Q(role='student')),
        teachers=Count('id', filter=Q(role='teacher')),
        admins=Count('id', filter=Q(role='admin')),
        assistants=Count('id', filter=Q(role='assistant_admin')),
        blocked=Count('id', filter=Q(is_blocked=True)),
        premium=Count('id', filter=Q(is_premium=True)),
        finished=Count('id', filter=Q(is_finished=True)),
        new_today=Count('id', filter=Q(date_joined__gte=today_start)),
        new_week=Count('id', filter=Q(date_joined__gte=today_start - timedelta(days=7))),
        online_now=Count('id', filter=Q(last_activity__gte=now - _ONLINE_WINDOW)),
    )
    return json.dumps({'stats': agg}, ensure_ascii=False), []


def tool_list_users(role=None, status=None, limit=15, order='newest'):
    """Foydalanuvchilar ro'yxati: rol/status bo'yicha, saralash bilan."""
    CustomUser = _user_model()
    qs = _apply_list_filters(CustomUser.objects.all(), role=role, status=status)

    order_map = {
        'newest': '-date_joined',
        'oldest': 'date_joined',
        'name': 'first_name',
        'name_desc': '-first_name',
        'activity': '-last_activity',
    }
    qs = qs.order_by(order_map.get(order, '-date_joined'))
    users = list(qs[:min(int(limit or 15), MAX_LIST_RESULTS)])

    if not users:
        return json.dumps({'users': [], 'note': 'Filtrga mos foydalanuvchi topilmadi.'},
                          ensure_ascii=False), []

    rows, links = [], []
    for u in users:
        rows.append(_user_row(u, extra={
            'joined': timezone.localtime(u.date_joined).strftime('%d.%m.%Y'),
            'profile_url': _user_url(u.pk),
        }))
        lnk = _user_link(u)
        if lnk:
            links.append(lnk)
    return json.dumps({'count': len(rows), 'users': rows}, ensure_ascii=False), links


def tool_get_online_users(limit=10):
    """Hozir onlayn bo'lgan foydalanuvchilar (oxirgi 5 daqiqa faollik)."""
    CustomUser = _user_model()
    qs = _apply_list_filters(CustomUser.objects.all(), online=True).order_by('-last_activity')
    users = list(qs[:min(int(limit or 10), MAX_LIST_RESULTS)])
    if not users:
        return json.dumps({'online': [], 'note': 'Hozir hech kim onlayn emas.'},
                          ensure_ascii=False), []
    rows = []
    for u in users:
        mins = int((timezone.now() - u.last_activity).total_seconds() // 60) if u.last_activity else None
        rows.append(_user_row(u, extra={
            'last_activity_minutes_ago': mins,
            'profile_url': _user_url(u.pk),
        }))
    return json.dumps({'online_count_shown': len(rows), 'online': rows}, ensure_ascii=False), []


# ── HARAKAT (ACTION) TOOLLARI ──────────────────────────────────────────────
def tool_block_user(user_id):
    """Foydalanuvchini bloklash (admin/superuser bloklanmaydi)."""
    CustomUser = _user_model()
    try:
        u = CustomUser.objects.get(pk=int(user_id))
    except (CustomUser.DoesNotExist, ValueError, TypeError):
        return json.dumps({'error': 'Foydalanuvchi topilmadi.'}, ensure_ascii=False), []
    if _is_protected(u):
        return json.dumps({'error': 'Admin hisobini bloklash mumkin emas.'},
                          ensure_ascii=False), []
    if u.is_blocked:
        return json.dumps({'success': True, 'already': True, 'user': _user_name(u),
                           'note': 'Foydalanuvchi allaqachon bloklangan.'},
                          ensure_ascii=False), []
    u.is_blocked = True
    u.save(update_fields=['is_blocked'])
    return json.dumps({'success': True, 'action': 'blocked', 'user': _user_name(u),
                       'user_id': u.pk,
                       'note': 'Foydalanuvchi muvaffaqiyatli bloklandi.'},
                      ensure_ascii=False), []


def tool_unblock_user(user_id):
    """Foydalanuvchini blokdan chiqarish."""
    CustomUser = _user_model()
    try:
        u = CustomUser.objects.get(pk=int(user_id))
    except (CustomUser.DoesNotExist, ValueError, TypeError):
        return json.dumps({'error': 'Foydalanuvchi topilmadi.'}, ensure_ascii=False), []
    if not u.is_blocked:
        return json.dumps({'success': True, 'already': True, 'user': _user_name(u),
                           'note': 'Foydalanuvchi bloklangan emas edi.'},
                          ensure_ascii=False), []
    CustomUser.objects.filter(pk=u.pk).update(is_blocked=False)
    return json.dumps({'success': True, 'action': 'unblocked', 'user': _user_name(u),
                       'user_id': u.pk,
                       'note': 'Foydalanuvchi blokdan chiqarildi.'},
                      ensure_ascii=False), []


def tool_set_finished(user_id, finished=True):
    """O'quvchini 'kursni tugatgan' deb belgilash yoki belgisini olib tashlash."""
    CustomUser = _user_model()
    try:
        u = CustomUser.objects.get(pk=int(user_id))
    except (CustomUser.DoesNotExist, ValueError, TypeError):
        return json.dumps({'error': 'Foydalanuvchi topilmadi.'}, ensure_ascii=False), []
    CustomUser.objects.filter(pk=u.pk).update(is_finished=bool(finished))
    action = 'marked_finished' if finished else 'unmarked_finished'
    return json.dumps({'success': True, 'action': action, 'user': _user_name(u),
                       'user_id': u.pk,
                       'note': ('Kursni tugatgan deb belgilandi.' if finished
                                else "Tugatgan belgisi olib tashlandi.")},
                      ensure_ascii=False), []


def tool_update_user_names(user_id, first_name=None, last_name=None):
    """Foydalanuvchining ism/familiyasini yangilash."""
    CustomUser = _user_model()
    try:
        u = CustomUser.objects.get(pk=int(user_id))
    except (CustomUser.DoesNotExist, ValueError, TypeError):
        return json.dumps({'error': 'Foydalanuvchi topilmadi.'}, ensure_ascii=False), []
    old = f"{u.first_name} {u.last_name}".strip()
    updates = {}
    if first_name is not None:
        updates['first_name'] = str(first_name).strip()[:100]
    if last_name is not None:
        updates['last_name'] = str(last_name).strip()[:100]
    if not updates:
        return json.dumps({'error': "Yangi ism yoki familiya berilmadi."},
                          ensure_ascii=False), []
    CustomUser.objects.filter(pk=u.pk).update(**updates)
    u.refresh_from_db()
    return json.dumps({'success': True, 'action': 'renamed', 'user_id': u.pk,
                       'old_name': old,
                       'new_name': f"{u.first_name} {u.last_name}".strip(),
                       'note': 'Ism muvaffaqiyatli yangilandi.'},
                      ensure_ascii=False), []


def tool_bulk_fix_names(mode='capitalize'):
    """BARCHA foydalanuvchilar ismlarini tuzatish.

    mode='capitalize' — har bir so'zning birinchi harfini katta, qolganini
    kichik harfga o'tkazadi ("ali VALIYEV" -> "Ali Valiyev")."""
    CustomUser = _user_model()
    if mode != 'capitalize':
        return json.dumps({'error': "Faqat mode='capitalize' qo'llab-quvvatlanadi."},
                          ensure_ascii=False), []

    def fix(value):
        return ' '.join(w.capitalize() for w in (value or '').split() if w)

    changed, samples, scanned = 0, [], 0
    qs = CustomUser.objects.only('id', 'first_name', 'last_name')
    for u in qs.iterator(chunk_size=500):
        scanned += 1
        nf, nl = fix(u.first_name), fix(u.last_name)
        if nf != (u.first_name or '') or nl != (u.last_name or ''):
            if changed < MAX_BULK_UPDATES:
                CustomUser.objects.filter(pk=u.pk).update(first_name=nf, last_name=nl)
                if len(samples) < 8:
                    samples.append({
                        'old': f"{u.first_name} {u.last_name}".strip(),
                        'new': f"{nf} {nl}".strip(),
                    })
            changed += 1
    return json.dumps({
        'success': True, 'action': 'bulk_fix_names',
        'scanned': scanned, 'changed': changed,
        'samples': samples,
        'note': (f"{changed} ta foydalanuvchining ismi tuzatildi "
                 f"(jami ko'rilgan: {scanned})."),
    }, ensure_ascii=False), []


def tool_delete_user(user_id, confirm=False):
    """Foydalanuvchini O'CHIRISH — faqat admin aniq buyruq berganda (confirm=True).
    Admin/superuser hisoblari o'chirilmaydi."""
    CustomUser = _user_model()
    try:
        u = CustomUser.objects.get(pk=int(user_id))
    except (CustomUser.DoesNotExist, ValueError, TypeError):
        return json.dumps({'error': 'Foydalanuvchi topilmadi.'}, ensure_ascii=False), []
    if _is_protected(u):
        return json.dumps({'error': 'Admin hisobini o\'chirish mumkin emas.'},
                          ensure_ascii=False), []
    if not confirm:
        return json.dumps({'needs_confirmation': True,
                           'note': ("Bu qaytarib bo'lmaydigan amal. Admin "
                                    "'o'chirishni tasdiqlayman' deganda bajariladi.")},
                          ensure_ascii=False), []
    name = _user_name(u)
    u.delete()
    return json.dumps({'success': True, 'action': 'deleted', 'user': name,
                       'note': f'{name} tizimdan o\'chirildi.'},
                      ensure_ascii=False), []


TOOLS = {
    'search_users': (tool_search_users, {
        "type": "function",
        "function": {
            "name": "search_users",
            "description": "Foydalanuvchini ism, familiya, username, telefon yoki student_id "
                           "bo'yicha qidiradi. Savol yoki buyruqdagi ismni user_id'ga "
                           "aylantirish uchun avval shuni chaqiring.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Ism yoki uning bir qismi"},
                    "limit": {"type": "integer", "description": "Nechta natija (max 30)"},
                },
                "required": ["query"],
            },
        },
    }),
    'get_user_profile': (tool_get_user_profile, {
        "type": "function",
        "function": {
            "name": "get_user_profile",
            "description": "Foydalanuvchining TO'LIQ profilini qaytaradi: telefon, rol, status, "
                           "guruhlar, yo'nalish, premium, tanga, telegram, qo'shilgan sana, "
                           "oxirgi faollik va h.k. 'Axmat haqida malumot ber' kabi savollar uchun.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "search_users dan olingan id"},
                },
                "required": ["user_id"],
            },
        },
    }),
    'get_user_stats': (tool_get_user_stats, {
        "type": "function",
        "function": {
            "name": "get_user_stats",
            "description": "Tizimdagi foydalanuvchilar statistikasi: jami, o'quvchilar, "
                           "o'qituvchilar, bloklanganlar, premium, onlayn, bugun qo'shilganlar. "
                           "'Nechta foydalanuvchi bor?' kabi savollar uchun.",
            "parameters": {"type": "object", "properties": {}},
        },
    }),
    'list_users': (tool_list_users, {
        "type": "function",
        "function": {
            "name": "list_users",
            "description": "Foydalanuvchilar ro'yxatini qaytaradi (rol/status bo'yicha filtr, "
                           "saralash bilan). 'Yangi foydalanuvchilar', 'bloklanganlar ro'yxati', "
                           "'o'quvchilar ro'yxati' kabi so'rovlar uchun.",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {"type": "string", "enum": ["student", "teacher", "admin", "assistant_admin"],
                             "description": "Rol filtri (ixtiyoriy)"},
                    "status": {"type": "string", "enum": ["active", "blocked"],
                               "description": "Status filtri (ixtiyoriy)"},
                    "limit": {"type": "integer", "description": "Nechta natija (max 30)"},
                    "order": {"type": "string",
                              "enum": ["newest", "oldest", "name", "name_desc", "activity"],
                              "description": "Saralash (ixtiyoriy)"},
                },
            },
        },
    }),
    'get_online_users': (tool_get_online_users, {
        "type": "function",
        "function": {
            "name": "get_online_users",
            "description": "Hozir onlayn bo'lgan foydalanuvchilar ro'yxati (oxirgi 5 daqiqa).",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Nechta natija (max 30)"},
                },
            },
        },
    }),
    'block_user': (tool_block_user, {
        "type": "function",
        "function": {
            "name": "block_user",
            "description": "Foydalanuvchini BLOKLAYDI (harakat). Admin aniq 'blokla' deganda "
                           "bajariladi. Admin hisoblarini bloklash mumkin emas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "search_users dan olingan id"},
                },
                "required": ["user_id"],
            },
        },
    }),
    'unblock_user': (tool_unblock_user, {
        "type": "function",
        "function": {
            "name": "unblock_user",
            "description": "Foydalanuvchini BLOKDAN CHIQARADI (harakat). "
                           "'blokdan chiqar' buyrug'i bilan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "search_users dan olingan id"},
                },
                "required": ["user_id"],
            },
        },
    }),
    'set_finished': (tool_set_finished, {
        "type": "function",
        "function": {
            "name": "set_finished",
            "description": "O'quvchini 'kursni tugatgan' deb belgilaydi yoki belgisini "
                           "olib tashlaydi (harakat).",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer"},
                    "finished": {"type": "boolean",
                                 "description": "true=belgilash, false=olib tashlash"},
                },
                "required": ["user_id"],
            },
        },
    }),
    'update_user_names': (tool_update_user_names, {
        "type": "function",
        "function": {
            "name": "update_user_names",
            "description": "Foydalanuvchining ism yoki familiyasini yangilaydi (harakat). "
                           "Masalan: 'Axmatning familiyasini Karimov qilib qo'y'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer"},
                    "first_name": {"type": "string", "description": "Yangi ism (ixtiyoriy)"},
                    "last_name": {"type": "string", "description": "Yangi familiya (ixtiyoriy)"},
                },
                "required": ["user_id"],
            },
        },
    }),
    'bulk_fix_names': (tool_bulk_fix_names, {
        "type": "function",
        "function": {
            "name": "bulk_fix_names",
            "description": "BARCHA foydalanuvchilarning ism-familiyasini tuzatadi: har bir "
                           "so'zning birinchi harfini katta qiladi (harakat). "
                           "'Ismlarni bosh harfini katta qilib chiq' buyrug'i bilan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["capitalize"],
                             "description": "Hozircha faqat 'capitalize'"},
                },
            },
        },
    }),
    'delete_user': (tool_delete_user, {
        "type": "function",
        "function": {
            "name": "delete_user",
            "description": "Foydalanuvchini butunlay O'CHIRADI (qaytarilmas harakat). "
                           "FAQAT admin aniq 'o'chir' deganda, confirm=true bilan chaqiring. "
                           "Ikkilanganingizda confirm=false yuborib tasdiq so'rang.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer"},
                    "confirm": {"type": "boolean",
                                "description": "Admin aniq tasdiqlaganda true"},
                },
                "required": ["user_id"],
            },
        },
    }),
}


def _dispatch_tool(name, args):
    """Tool chaqiruvini xavfsiz bajaradi; (json_matn, havolalar) qaytaradi."""
    entry = TOOLS.get(name)
    if not entry:
        return json.dumps({'error': f"Noma'lum vosita: {name}"}, ensure_ascii=False), []
    func = entry[0]
    try:
        return func(**args)
    except Exception as e:  # tool xatosi agent'ni to'xtatmasligi kerak
        # Xato matni OpenAI ga qaytib yuboriladi — DB jadval/ustun nomlari va
        # qator ma'lumotlari uchinchi tomonga chiqib ketmasin. To'liq izoh
        # server jurnalida qoladi.
        from .security import safe_error
        return json.dumps(
            {'error': safe_error(e, f'users_ai_tool:{name}', 'Ichki xatolik')},
            ensure_ascii=False,
        ), []


# ---------------------------------------------------------------------------
#  OpenAI agent
# ---------------------------------------------------------------------------
def _get_client():
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    if not api_key or not api_key.strip():
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key.strip(), timeout=60)
    except Exception as e:
        print(f"Users AI: OpenAI client yaratib bo'lmadi: {e}")
        return None


def _system_prompt():
    now = timezone.localtime()
    weekdays = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']
    return f"""Siz LMS admin panelining "AI Foydalanuvchi Boshqaruvchisi" modulisiz.
Vazifangiz — admin savollariga FOYDALANUVCHILAR bazasiga tayangan holda javob
berish HAMDA adminning aniq buyruqlarini (bloklash, blokdan chiqarish, ism
tuzatish, o'chirish va h.k.) bazada AMALGA OSHIRISH.
Har doim O'ZBEK tilida javob bering.

BUGUN: {now.strftime('%Y-%m-%d')} ({weekdays[now.weekday()]}), soat {now.strftime('%H:%M')}.

QOIDALAR:
1. FAQAT vositalar (tools) qaytargan ma'lumotlarga tayanib javob bering.
   Foydalanuvchi ma'lumotini O'ZINGIZ O'YLAB CHIQARMANG.
2. Savol yoki buyruqdagi ism uchun avval search_users chaqirib user_id oling.
3. HARAKAT BUYRUQLARI (block_user, unblock_user, set_finished, update_user_names,
   bulk_fix_names): admin aniq buyruq berganda darhol bajaring — ruxsat so'ramang.
   Admin noaniq yozsa (masalan bir nechta xuddi shu ismli bor), aniqlashtirib so'rang.
4. delete_user — FAQAT admin "o'chir" / "o'chirib yubor" deb aniq yozganda.
   Avval confirm=false bilan chaqirib tasdiq so'rang, admin tasdiqlaganda
   confirm=true bilan bajaring. Admin hisoblarini o'chirish/bloklash MUMKIN EMAS —
   buni rad eting.
5. Harakat bajarilgach javobda nima o'zgargani aniq yozing (kim, qanaqa amal) va
   "Ro'yxatni yangilash uchun sahifani yangilang (F5)" deb eslatib qo'ying.
6. Profilga havolalarni FAQAT vositalar qaytargan profile_url'dan oling va
   markdown ko'rinishida yozing: [Ism](profile_url)
7. Javob tuzilishi: avval 1-2 gaplik xulosa, kerak bo'lsa qisqa ro'yxat,
   oxirida havola(lar). Katta ro'yxatni 10-15 tadan oshib ko'chirmang —
   "yana bor" deb yozing.
8. Telefon, passport kabi shaxsiy ma'lumotlarni faqat admin so'raganda ko'rsating.
9. Hech narsa topilmasa ochiq ayting va aniqlashtiruvchi savol taklif qiling.
10. Qisqa, rasmiy-do'stona ohangda yozing.
"""


def _run_openai_agent(client, question, history=None):
    """Function-calling agent sikli. Natija: {'answer','links','mode','tools_used','ok'}."""
    messages = [{"role": "system", "content": _system_prompt()}]

    for item in (history or [])[-4:]:
        q = (item.get('q') or '').strip()
        a = (item.get('a') or '').strip()
        if q:
            messages.append({"role": "user", "content": q[:500]})
        if a:
            messages.append({"role": "assistant", "content": a[:1200]})

    messages.append({"role": "user", "content": question})

    tool_specs = [spec for _fn, spec in TOOLS.values()]
    links, tools_used = [], []

    for _step in range(AGENT_MAX_STEPS):
        try:
            resp = client.chat.completions.create(
                model=AI_MODEL,
                messages=messages,
                tools=tool_specs,
                tool_choice="auto",
                temperature=AI_TEMPERATURE,
                max_tokens=AI_MAX_TOKENS,
            )
        except Exception as e:
            # OpenAI SDK xatoligi so'rov URL i, model va tashkilot ID sini
            # o'z ichiga oladi — brauzerga chiqarilmasin.
            from .security import safe_error
            return {
                'answer': "⚠️ " + safe_error(
                    e, 'users_ai_openai', "AI xizmatiga ulanishda xatolik. Keyinroq urinib ko'ring.",
                ),
                'links': [], 'mode': 'openai', 'tools_used': tools_used, 'ok': False,
            }

        msg = resp.choices[0].message

        if getattr(msg, 'tool_calls', None):
            messages.append(msg)
            for call in msg.tool_calls:
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments or '{}')
                except ValueError:
                    args = {}
                result_json, found_links = _dispatch_tool(name, args)
                tools_used.append(name)
                links.extend(found_links)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result_json,
                })
            continue

        answer = (msg.content or '').strip()
        return {
            'answer': answer or "Javob olinmadi.",
            'links': _dedupe_links(links),
            'mode': 'openai',
            'tools_used': tools_used,
            'ok': True,
        }

    return {
        'answer': "⚠️ Agent juda ko'p qadam bajardi — savolni soddaroq qilib qayta yozing.",
        'links': _dedupe_links(links), 'mode': 'openai', 'tools_used': tools_used, 'ok': False,
    }


def _dedupe_links(links):
    seen, out = set(), []
    for l in links:
        if l['url'] in seen:
            continue
        seen.add(l['url'])
        out.append(l)
    return out


# ---------------------------------------------------------------------------
#  Offline fallback (API kalit bo'lmasa) — qoidaviy yordamchi
# ---------------------------------------------------------------------------
_QUESTION_WORDS = {
    'nechta', 'nechchi', 'qancha', 'kim', 'kimlar', 'bor', 'bormi', 'hamma',
    'barcha', 'barisi', 'royxatini', "ro'yxatini", 'korsat', "ko'rsat", 'korib',
    "ko'rib", 'chiqarib', 'chiq', 'qilib', 'qil', 'bilan', 'haqida', 'malumot',
    "ma'lumot", 'malumotlar', "ma'lumotlar", 'ber', 'aysan', 'menda', 'tizimda',
    'bazada', 'hozir', 'bugun', 'kecha', 'shu', 'ushbu', 'tani', 'tanib',
    'ochir', "o'chir", 'ochirish', "o'chirish", 'blok', 'blokla', 'bloklangan',
    'bloklanganlar', 'blokdan', 'faol', 'faollar', 'onlayn', 'online', 'admin',
    'AI', 'ai', 'yordamchi', 'iltimos', 'va', 'ham', 'da', 'ni', 'ning', 'ga',
    'the', 'bor', 'edi', 'mikan', 'mikin',
}


def _extract_names(question):
    tokens = re.findall(r"[A-Za-zÀ-žʼ’'0-9]+", question)
    return [t for t in tokens if len(t) >= 3 and t.lower() not in _QUESTION_WORDS]


def _run_fallback(question):
    q = question.lower()

    def _md_list(rows, with_status=False):
        lines = []
        for r in rows:
            url = r.get('profile_url')
            name = r['name']
            entry = f"- [{name}]({url})" if url else f"- {name}"
            entry += f" — {r.get('role', '')}"
            if with_status:
                entry += ' — 🚫 Bloklangan' if r.get('blocked') else ' — ✅ Faol'
            if r.get('phone'):
                entry += f" — {r['phone']}"
            lines.append(entry)
        return lines

    # 1) "Ismlarni bosh harfini katta qilib chiq" — bulk amal
    if ('bosh harf' in q or 'katta harf' in q or 'kapital' in q) and ('ism' in q or 'familiya' in q):
        result_json, links = tool_bulk_fix_names('capitalize')
        data = json.loads(result_json)
        if data.get('error'):
            answer = f"⚠️ {data['error']}"
        else:
            answer = (f"✅ **Barcha ismlar tuzatildi!**\n\n"
                      f"- Ko'rilgan foydalanuvchi: **{data['scanned']}**\n"
                      f"- O'zgargan: **{data['changed']}**\n\n")
            if data.get('samples'):
                answer += "Namunalar:\n"
                for s in data['samples'][:5]:
                    answer += f"- {s['old']} → **{s['new']}**\n"
            answer += "\n*Sahifani yangilang (F5) — ro'yxatda yangi ismlar ko'rinadi.*"
        return {'answer': answer, 'links': [], 'mode': 'fallback',
                'tools_used': ['bulk_fix_names'], 'ok': True}

    # 2) Blokdan chiqarish / bloklash buyrug'i
    names = _extract_names(question)
    if names and ('blokdan chiqar' in q or 'blokdan ozod' in q):
        users = _find_users(' '.join(names[:2]))
        if users:
            u = users[0]
            if _is_protected(u):
                answer = f"⚠️ {_user_name(u)} — admin hisobi, uni bloklash/blokdan chiqarish mumkin emas."
                return _fb(answer, [])
            result_json, _ = tool_unblock_user(u.pk)
            data = json.loads(result_json)
            answer = (f"✅ **{_user_name(u)}** blokdan chiqarildi."
                      if data.get('success') and not data.get('already')
                      else f"ℹ️ {_user_name(u)} — {data.get('note', '')}")
            lnk = _user_link(u)
            return _fb(answer, [lnk] if lnk else [])
    if names and ('blokla' in q) and ('royxat' not in q and "ro'yxat" not in q and 'nechta' not in q):
        users = _find_users(' '.join(names[:2]))
        if users:
            u = users[0]
            if _is_protected(u):
                return _fb(f"⚠️ {_user_name(u)} — admin hisobini bloklash mumkin emas.", [])
            result_json, _ = tool_block_user(u.pk)
            data = json.loads(result_json)
            answer = (f"✅ **{_user_name(u)}** bloklandi." if data.get('success')
                      else f"⚠️ {data.get('error', 'Xatolik')}")
            lnk = _user_link(u)
            return _fb(answer, [lnk] if lnk else [])

    # 3) Statistika
    if any(w in q for w in ('nechta', 'nechchi', 'qancha', 'statistika')):
        result_json, _ = tool_get_user_stats()
        s = json.loads(result_json)['stats']
        answer = (
            f"📊 **Foydalanuvchilar statistikasi:**\n\n"
            f"- Jami: **{s['total']}**\n"
            f"- O'quvchilar: **{s['students']}**\n"
            f"- O'qituvchilar: **{s['teachers']}**\n"
            f"- Adminlar: **{s['admins']}** | Yordamchi adminlar: **{s['assistants']}**\n"
            f"- 🚫 Bloklangan: **{s['blocked']}**\n"
            f"- ⭐ Premium: **{s['premium']}** | 🎓 Kursni tugatgan: **{s['finished']}**\n"
            f"- 🟢 Hozir onlayn: **{s['online_now']}**\n"
            f"- Bugun qo'shilgan: **{s['new_today']}** (bu hafta: {s['new_week']})"
        )
        return _fb(answer, [])

    # 4) Bloklanganlar ro'yxati
    if 'bloklangan' in q:
        result_json, links = tool_list_users(status='blocked', limit=15)
        data = json.loads(result_json)
        rows = data.get('users', [])
        if not rows:
            answer = "Hozircha bloklangan foydalanuvchi yo'q. ✅"
        else:
            answer = f"🚫 **Bloklangan foydalanuvchilar ({len(rows)}):**\n\n"
            answer += '\n'.join(_md_list(rows))
            if data.get('count', len(rows)) >= 15:
                answer += "\n\n*(boshqalar ham bor — sahifadai *Bloklangan* filtri bilan ko'ring)*"
        return _fb(answer, links)

    # 5) Onlayn foydalanuvchilar
    if 'onlayn' in q or 'online' in q:
        result_json, links = tool_get_online_users(10)
        data = json.loads(result_json)
        rows = data.get('online', [])
        if not rows:
            answer = "Hozir hech kim onlayn emas."
        else:
            answer = f"🟢 **Hozir onlayn ({len(rows)}):**\n\n"
            answer += '\n'.join(f"- [{r['name']}]({r['profile_url']}) — {r['role']}"
                                if r.get('profile_url') else f"- {r['name']}" for r in rows)
        return _fb(answer, links)

    # 6) Ism bo'yicha qidiruv / profil
    if names:
        users = _find_users(' '.join(names[:3]))
        if users:
            result_json, links = tool_get_user_profile(users[0].pk)
            data = json.loads(result_json)
            p = data.get('profile', {})
            if p:
                answer = (
                    f"👤 **{p['name']}** ({p['role']})\n\n"
                    f"- Username: @{p['username']}"
                    + (f" | ID: #{p['student_id']}" if p.get('student_id') else "") + "\n"
                    + (f"- Telefon: {p['phone']}\n" if p.get('phone') else "")
                    + f"- Status: {'🚫 Bloklangan' if p['blocked'] else '✅ Faol'}"
                    + (f" | 🎓 Kursni tugatgan" if p.get('finished_course') else "") + "\n"
                    + (f"- Guruhlar: {', '.join(p['groups'])}\n" if p.get('groups') else "")
                    + (f"- Qo'shilgan: {p['joined_at']}\n" if p.get('joined_at') else "")
                    + (f"- Oxirgi faollik: {p['last_activity']}" if p.get('last_activity') else "")
                )
                return _fb(answer, links)

    # 7) Umumiy yordam
    answer = (
        "Savolingizni tushunmadim. Quyidagicha so'rang yoki buyruq bering:\n"
        "- *Nechta bloklangan foydalanuvchi bor?*\n"
        "- *Barcha ismlarni bosh harfini katta qilib chiq*\n"
        "- *Axmatni blokdan chiqar*\n"
        "- *Madina haqida ma'lumot ber*\n"
        "- *Bloklanganlar ro'yxatini ko'rsat*\n\n"
        "ℹ️ To'liq AI rejimi uchun OPENAI_API_KEY sozlanishi kerak."
    )
    return _fb(answer, [])


def _fb(answer, links):
    return {'answer': answer, 'links': _dedupe_links(links or []), 'mode': 'fallback',
            'tools_used': [], 'ok': True}


# ---------------------------------------------------------------------------
#  Kirish nuqtasi
# ---------------------------------------------------------------------------
def analyze_users(question, history=None):
    """Admin savoliga javob qaytaradi.

    Qaytaradi: {'answer': markdown str, 'links': [{'url','label'}],
                'mode': 'openai'|'fallback', 'tools_used': [...], 'ok': bool}
    """
    question = (question or '').strip()
    if not question:
        return {'answer': "Savol bo'sh.", 'links': [], 'mode': 'none', 'tools_used': [], 'ok': False}

    client = _get_client()
    if client:
        return _run_openai_agent(client, question, history)
    return _run_fallback(question)


def ai_available():
    """OpenAI kaliti sozlanganmi — UI'da badge ko'rsatish uchun."""
    return bool((getattr(settings, 'OPENAI_API_KEY', '') or '').strip())
