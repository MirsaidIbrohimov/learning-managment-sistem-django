"""AI Çat Tahlilçi — admin paneldagi "Şaxsiy çatlar" sahifasi uçun
sun'iy intellekt tahlil dvijoki.

Ikki rejimda işlaydi:

1. **OpenAI agent rejimi** (OPENAI_API_KEY sozlangan bölsa):
   GPT modeli function-calling orqali quyidagi vositalarni özi tanlab
   çaqiradi: foydalanuvçi qidiriş, suhbatdoştlar röyxati, xabarlar
   böyiça qidiruv, suhbat tarkibini öqiş. Javob özbek tilida,
   çat havolalari (markdown linklar) bilan qaytariladi.

2. **Offline fallback rejimi** (API kalit yöq bölsa):
   Eng köp söraladigan savol turlarini ("X kimlar bilan yozişdi bugun?",
   "... mavzusida kimlar gaplaşibdi?") oddiy qoidalar asosida tahlil qiladi.

Maxfiylik: admin / yordamchi-admin rollaridagi foydalanuvçilarning xabarlari
tahlilga HEÇ QAÇON kiritilmaydi (queryset darajasida çiqarib taşlanadi) —
bu monitoring sahifasining umumiy qoidasi bilan bir xil.
"""
import json
import re
from datetime import datetime, timedelta, time as dt_time

from django.conf import settings
from django.db.models import Q, Count, Max, F, Case, When, IntegerField
from django.urls import reverse
from django.utils import timezone

from .alphabet import to_new_alphabet

# ---------------------------------------------------------------------------
#  Konfiguratsiya
# ---------------------------------------------------------------------------
AI_MODEL = "gpt-4o-mini"
AI_MAX_TOKENS = 1600
AI_TEMPERATURE = 0.2
AGENT_MAX_STEPS = 6          # agent eng köpi bilan şunça tool-chaqiruv qiladi
MAX_MSGS_PER_TOOL = 30       # bitta tool javobidagi maksimal xabarlar soni
MSG_PREVIEW_CHARS = 220      # bitta xabarning maksimal uzunligi (qisqartiriş)
MAX_SEARCH_RESULTS = 40

_PRIVATE_ROLES = ('admin', 'assistant_admin')

_ROLE_LABELS = {
    'student': "Öquvçi",
    'teacher': "Öqituvçi",
    'admin': 'Admin',
    'assistant_admin': 'Yordamçi admin',
}


# ---------------------------------------------------------------------------
#  Umumiy yordamçilar
# ---------------------------------------------------------------------------
def _models():
    """Circular import'dan qoçiş uçun keçiktirilgan import."""
    from .models import CustomUser, DirectMessage
    return CustomUser, DirectMessage


def _base_qs():
    """Tahlil uçun ruxsat etilgan şaxsiy xabarlar.

    Adminlar çiqarib taşlanadi (maxfiylik). Foydalanuvçi ÖÇIRGAN xabarlar
    esa kiritiladi — investigatsiya maqsadida, ammo har doim 🗑 belgisi bilan
    körsatiladi (AI javobda ham buni qayd etişi kerak)."""
    _, DirectMessage = _models()
    return (
        DirectMessage.objects
        .exclude(sender__role__in=_PRIVATE_ROLES)
        .exclude(recipient__role__in=_PRIVATE_ROLES)
    )


def _chat_url(u1_pk, u2_pk):
    return reverse('admin_direct_chat_detail', kwargs={'u1_pk': u1_pk, 'u2_pk': u2_pk})


def _role_label(user):
    return _ROLE_LABELS.get(user.role, user.role)


def _user_label(user):
    name = (user.full_name or '').strip() or user.username
    return f"{name} ({_role_label(user)})"


def _pair_order(a, b):
    return (a, b) if a < b else (b, a)


def _parse_date(value):
    """'YYYY-MM-DD' matnini date'ga ötkazadi; xato bölsa None."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value.strip()[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


def _period_filter(qs, date_from, date_to):
    """Queryset'ni [date_from, date_to] kun oraliği böyiça çeklaydi."""
    if date_from:
        start = timezone.make_aware(datetime.combine(date_from, dt_time.min))
        qs = qs.filter(created_at__gte=start)
    if date_to:
        end = timezone.make_aware(datetime.combine(date_to, dt_time.max))
        qs = qs.filter(created_at__lte=end)
    return qs


def _clip(text):
    text = (text or '').strip()
    if not text:
        return '[fayl]'
    if len(text) > MSG_PREVIEW_CHARS:
        return text[:MSG_PREVIEW_CHARS].rstrip() + '…'
    return text


def _find_users(query, limit=6):
    """Ism/familiya/username böyiça foydalanuvçi qidiriş (adminlarsiz)."""
    CustomUser, _ = _models()
    query = (query or '').strip()
    if not query:
        return []
    q = Q()
    for token in query.split():
        if len(token) < 2:
            continue
        q |= (Q(first_name__icontains=token) | Q(last_name__icontains=token)
              | Q(username__icontains=token))
    if not q:
        return []
    return list(
        CustomUser.objects.filter(q)
        .exclude(role__in=_PRIVATE_ROLES)
        .order_by('first_name', 'last_name')[:limit]
    )


# ---------------------------------------------------------------------------
#  TOOL implementatsiyalari — har biri (json_matn, havolalar) qaytaradi
# ---------------------------------------------------------------------------
def tool_find_users(query):
    users = _find_users(query)
    if not users:
        return json.dumps({'found': [], 'note': 'Bunday foydalanuvçi topilmadi.'},
                          ensure_ascii=False), []
    data = [{
        'user_id': u.pk,
        'name': (u.full_name or '').strip() or u.username,
        'username': u.username,
        'role': _role_label(u),
    } for u in users]
    return json.dumps({'found': data}, ensure_ascii=False), []


def tool_get_user_partners(user_id, date_from=None, date_to=None):
    """Berilgan foydalanuvçi körsatilgan davrda kimlar bilan yozişgani."""
    CustomUser, _ = _models()
    try:
        user = CustomUser.objects.get(pk=int(user_id))
    except (CustomUser.DoesNotExist, ValueError, TypeError):
        return json.dumps({'error': 'Foydalanuvçi topilmadi.'}, ensure_ascii=False), []

    d_from, d_to = _parse_date(date_from), _parse_date(date_to)
    qs = _base_qs().filter(Q(sender=user) | Q(recipient=user))
    qs = _period_filter(qs, d_from, d_to)

    partners = {}
    for row in qs.values('sender_id', 'recipient_id', 'created_at', 'message', 'is_deleted'):
        other_id = row['recipient_id'] if row['sender_id'] == user.pk else row['sender_id']
        p = partners.setdefault(other_id, {'count': 0, 'last_at': None, 'samples': [], 'deleted': 0})
        p['count'] += 1
        if row['is_deleted']:
            p['deleted'] += 1
        if p['last_at'] is None or row['created_at'] > p['last_at']:
            p['last_at'] = row['created_at']
        if len(p['samples']) < 3 and row['message']:
            prefix = "🗑 [öchirilgan] " if row['is_deleted'] else ''
            p['samples'].append(prefix + _clip(row['message'])[:120])

    if not partners:
        period = _period_label(d_from, d_to)
        return json.dumps({
            'user': _user_label(user),
            'period': period,
            'partners': [],
            'note': f'{user.full_name or user.username} {period} heç kim bilan yozişmagan.',
        }, ensure_ascii=False), []

    users_by_id = CustomUser.objects.in_bulk(partners.keys())
    items, links = [], []
    for other_id, p in sorted(partners.items(), key=lambda kv: kv[1]['last_at'], reverse=True):
        other = users_by_id.get(other_id)
        if not other:
            continue
        u1, u2 = _pair_order(user.pk, other_id)
        url = _chat_url(u1, u2)
        label = f"{(user.full_name or user.username)} ↔ {(other.full_name or other.username)}"
        links.append({'url': url, 'label': label})
        items.append({
            'partner_id': other_id,
            'partner': _user_label(other),
            'messages': p['count'],
            'deleted_messages': p['deleted'],
            'last_message_at': timezone.localtime(p['last_at']).strftime('%d.%m.%Y %H:%M'),
            'sample_messages': p['samples'],
            'chat_url': url,
        })

    return json.dumps({
        'user': _user_label(user),
        'period': _period_label(d_from, d_to),
        'partners_count': len(items),
        'partners': items,
    }, ensure_ascii=False), links


def tool_search_messages(keyword, date_from=None, date_to=None, user_id=None, limit=MAX_SEARCH_RESULTS):
    """Barça şaxsiy xabarlarda kalit söz (yoki sözlar) böyiça qidiruv."""
    keyword = (keyword or '').strip()
    if not keyword:
        return json.dumps({'error': "Kalit söz kiritilmagan."}, ensure_ascii=False), []

    d_from, d_to = _parse_date(date_from), _parse_date(date_to)
    qs = _base_qs()
    words = [w for w in keyword.split() if len(w) >= 2][:5]
    if not words:
        words = [keyword]
    q = Q()
    for w in words:
        q |= Q(message__icontains=w)
    qs = qs.filter(q)
    if user_id:
        CustomUser, _ = _models()
        try:
            u = CustomUser.objects.get(pk=int(user_id))
            qs = qs.filter(Q(sender=u) | Q(recipient=u))
        except (CustomUser.DoesNotExist, ValueError, TypeError):
            pass
    qs = _period_filter(qs, d_from, d_to).select_related('sender', 'recipient').order_by('-created_at')

    rows = list(qs[:limit])
    if not rows:
        return json.dumps({
            'keyword': keyword, 'matches': [],
            'period': _period_label(d_from, d_to),
            'note': f'"{keyword}" böyiça {_period_label(d_from, d_to)} heç narsa topilmadi.',
        }, ensure_ascii=False), []

    matches, links, seen_pairs = [], [], set()
    for m in rows:
        u1, u2 = _pair_order(m.sender_id, m.recipient_id)
        url = _chat_url(u1, u2)
        pair_label = f"{(m.sender.full_name or m.sender.username)} ↔ {(m.recipient.full_name or m.recipient.username)}"
        if (u1, u2) not in seen_pairs:
            seen_pairs.add((u1, u2))
            links.append({'url': url, 'label': pair_label})
        matches.append({
            'from': (m.sender.full_name or m.sender.username),
            'to': (m.recipient.full_name or m.recipient.username),
            'text': ("🗑 [öchirilgan xabar] " if m.is_deleted else '') + _clip(m.message),
            'deleted': m.is_deleted,
            'at': timezone.localtime(m.created_at).strftime('%d.%m.%Y %H:%M'),
            'chat_url': url,
        })

    return json.dumps({
        'keyword': keyword,
        'period': _period_label(d_from, d_to),
        'total_shown': len(matches),
        'matches': matches,
    }, ensure_ascii=False), links


def tool_get_conversation(user1_id, user2_id, date_from=None, date_to=None, limit=MAX_MSGS_PER_TOOL):
    """Ikki foydalanuvçi orasidagi suhbat mazmunini öqiş."""
    CustomUser, _ = _models()
    try:
        u1 = CustomUser.objects.get(pk=int(user1_id))
        u2 = CustomUser.objects.get(pk=int(user2_id))
    except (CustomUser.DoesNotExist, ValueError, TypeError):
        return json.dumps({'error': 'Foydalanuvçi topilmadi.'}, ensure_ascii=False), []
    if u1.role in _PRIVATE_ROLES or u2.role in _PRIVATE_ROLES:
        return json.dumps({'error': 'Bu suhbat maxfiy (admin iştirokida).'}, ensure_ascii=False), []

    d_from, d_to = _parse_date(date_from), _parse_date(date_to)
    qs = _base_qs().filter(Q(sender=u1, recipient=u2) | Q(sender=u2, recipient=u1))
    qs = _period_filter(qs, d_from, d_to).select_related('sender').order_by('-created_at')
    rows = list(qs[:min(int(limit or MAX_MSGS_PER_TOOL), MAX_MSGS_PER_TOOL)])
    rows.reverse()

    a, b = _pair_order(u1.pk, u2.pk)
    url = _chat_url(a, b)
    label = f"{(u1.full_name or u1.username)} ↔ {(u2.full_name or u2.username)}"

    if not rows:
        return json.dumps({
            'conversation': label, 'messages': [],
            'note': f'{label} — {_period_label(d_from, d_to)} xabarlar topilmadi.',
            'chat_url': url,
        }, ensure_ascii=False), [{'url': url, 'label': label}]

    msgs = [{
        'from': (m.sender.full_name or m.sender.username),
        'text': ("🗑 [öchirilgan xabar] " if m.is_deleted else '') + _clip(m.message),
        'deleted': m.is_deleted,
        'edited': m.is_edited,
        'at': timezone.localtime(m.created_at).strftime('%d.%m.%Y %H:%M'),
    } for m in rows]

    return json.dumps({
        'conversation': label,
        'period': _period_label(d_from, d_to),
        'messages_shown': len(msgs),
        'messages': msgs,
        'chat_url': url,
    }, ensure_ascii=False), [{'url': url, 'label': label}]


def tool_get_top_conversations(date_from=None, date_to=None, limit=10):
    """Eng faol suhbatlar reytingi (körsatilgan davr uçun)."""
    d_from, d_to = _parse_date(date_from), _parse_date(date_to)
    qs = _period_filter(_base_qs(), d_from, d_to)

    pairs = (
        qs.annotate(
            p1=Case(When(sender_id__lt=F('recipient_id'), then=F('sender_id')),
                    default=F('recipient_id'), output_field=IntegerField()),
            p2=Case(When(sender_id__lt=F('recipient_id'), then=F('recipient_id')),
                    default=F('sender_id'), output_field=IntegerField()),
        )
        .values('p1', 'p2')
        .annotate(msg_count=Count('id'), last_at=Max('created_at'))
        .order_by('-msg_count')[:min(int(limit or 10), 20)]
    )

    CustomUser, _ = _models()
    ids = set()
    for p in pairs:
        ids.add(p['p1']); ids.add(p['p2'])
    users_by_id = CustomUser.objects.in_bulk(ids)

    items, links = [], []
    for p in pairs:
        a, b = users_by_id.get(p['p1']), users_by_id.get(p['p2'])
        if not a or not b:
            continue
        url = _chat_url(a.pk, b.pk)
        label = f"{(a.full_name or a.username)} ↔ {(b.full_name or b.username)}"
        links.append({'url': url, 'label': label})
        items.append({
            'pair': f"{_user_label(a)} ↔ {_user_label(b)}",
            'messages': p['msg_count'],
            'last_message_at': timezone.localtime(p['last_at']).strftime('%d.%m.%Y %H:%M'),
            'chat_url': url,
        })

    if not items:
        return json.dumps({'period': _period_label(d_from, d_to), 'top': [],
                           'note': f"{_period_label(d_from, d_to)} suhbatlar yöq."},
                          ensure_ascii=False), []
    return json.dumps({'period': _period_label(d_from, d_to), 'top': items}, ensure_ascii=False), links


def _period_label(d_from, d_to):
    today = timezone.localdate()
    if d_from and d_to and d_from == d_to:
        if d_from == today:
            return 'bugun'
        if d_from == today - timedelta(days=1):
            return 'keça'
        return d_from.strftime('%d.%m.%Y') + ' kuni'
    if d_from and d_to:
        return f"{d_from.strftime('%d.%m.%Y')}—{d_to.strftime('%d.%m.%Y')} oraliğida"
    if d_from:
        return f"{d_from.strftime('%d.%m.%Y')} dan boşlab"
    if d_to:
        return f"{d_to.strftime('%d.%m.%Y')} gaça"
    return 'barça vaqt'


TOOLS = {
    'find_users': (tool_find_users, {
        "type": "function",
        "function": {
            "name": "find_users",
            "description": "Ism, familiya yoki username böyiça foydalanuvçi qidiradi. "
                           "Savoldagi ismni user_id'ga aylantiriş uçun avval şuni çaqiring.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Ism yoki uning bir qismi, masalan 'Axmat'"},
                },
                "required": ["query"],
            },
        },
    }),
    'get_user_partners': (tool_get_user_partners, {
        "type": "function",
        "function": {
            "name": "get_user_partners",
            "description": "Foydalanuvçi körsatilgan davrda kimlar bilan yozişganini, "
                           "har biri bilan neçta xabar almaşganini qaytaradi.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "find_users dan olingan user_id"},
                    "date_from": {"type": "string", "description": "YYYY-MM-DD (ixtiyoriy)"},
                    "date_to": {"type": "string", "description": "YYYY-MM-DD (ixtiyoriy)"},
                },
                "required": ["user_id"],
            },
        },
    }),
    'search_messages': (tool_search_messages, {
        "type": "function",
        "function": {
            "name": "search_messages",
            "description": "Barça şaxsiy xabarlarda kalit söz/mavzu böyiça qidiradi va "
                           "topilgan xabarlar + çat havolalarini qaytaradi. "
                           "Mavzu böyiça savollar uçun (masalan 'sevgi haqida kimlar gaplaşibdi?').",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "Qidiriladigan söz yoki ibora"},
                    "date_from": {"type": "string", "description": "YYYY-MM-DD (ixtiyoriy)"},
                    "date_to": {"type": "string", "description": "YYYY-MM-DD (ixtiyoriy)"},
                    "user_id": {"type": "integer", "description": "Faqat şu foydalanuvçi xabarlarida (ixtiyoriy)"},
                },
                "required": ["keyword"],
            },
        },
    }),
    'get_conversation': (tool_get_conversation, {
        "type": "function",
        "function": {
            "name": "get_conversation",
            "description": "Ikki foydalanuvçi orasidagi suhbat mazmunini öqiydi — "
                           "'ular nima haqida gaplaşgan?' kabi savollar uçun.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user1_id": {"type": "integer"},
                    "user2_id": {"type": "integer"},
                    "date_from": {"type": "string", "description": "YYYY-MM-DD (ixtiyoriy)"},
                    "date_to": {"type": "string", "description": "YYYY-MM-DD (ixtiyoriy)"},
                    "limit": {"type": "integer", "description": "Xabarlar soni (max 30)"},
                },
                "required": ["user1_id", "user2_id"],
            },
        },
    }),
    'get_top_conversations': (tool_get_top_conversations, {
        "type": "function",
        "function": {
            "name": "get_top_conversations",
            "description": "Eng faol suhbatlar reytingini qaytaradi (davr böyiça filtr mumkin). "
                           "'Bugun eng faol çatlar qaysi?' kabi savollar uçun.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "YYYY-MM-DD (ixtiyoriy)"},
                    "date_to": {"type": "string", "description": "YYYY-MM-DD (ixtiyoriy)"},
                    "limit": {"type": "integer", "description": "Neçta natija (max 20)"},
                },
            },
        },
    }),
}


def _dispatch_tool(name, args):
    """Tool çaqiruvini xavfsiz bajaradi; (json_matn, havolalar) qaytaradi."""
    entry = TOOLS.get(name)
    if not entry:
        return json.dumps({'error': f"Noma'lum vosita: {name}"}, ensure_ascii=False), []
    func = entry[0]
    try:
        return func(**args)
    except Exception as e:  # tool xatosi agent'ni töxtatmasligi kerak
        # Xato matni OpenAI ga qaytib yuboriladi — DB jadval/ustun nomlari va
        # qator ma'lumotlari uçinçi tomonga çiqib ketmasin. Töliq izoh
        # server jurnalida qoladi.
        from .security import safe_error
        return json.dumps(
            {'error': safe_error(e, f'chat_ai_tool:{name}', 'Içki xatolik')},
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
        print(f"Çat AI: OpenAI client yaratib bölmadi: {e}")
        return None


def _system_prompt():
    now = timezone.localtime()
    weekdays = ['Duşanba', 'Seşanba', 'Çorşanba', 'Payşanba', 'Juma', 'Şanba', 'Yakşanba']
    return f"""Siz LMS admin panelining "AI Çat Tahlilçi" modulisiz. Vazifangiz — admin savollariga
şaxsiy çatlar (DirectMessage) bazasiga tayangan holda, ANIQ va DALILLI javob beriş.
Har doim ÖZBEK tilida javob bering.

BUGUN: {now.strftime('%Y-%m-%d')} ({weekdays[now.weekday()]}), soat {now.strftime('%H:%M')}.
"bugun" = {now.strftime('%Y-%m-%d')}, "keça" = {(now - timedelta(days=1)).strftime('%Y-%m-%d')}.

QOIDALAR:
1. FAQAT vositalar (tools) qaytargan ma'lumotlarga tayanib javob bering. Özingiz foydalanuvçi,
   xabar yoki sana ÖYLAB ÇIQARMANG.
2. Savoldagi ism uçun avval find_users çaqiring. Bir neçta mos foydalanuvçi çiqsa,
   eng aniq mosini tanlang yoki admindan aniqlaştiriş sörang.
3. Javobda topilgan suhbatlarga albatta havola bering. Havolalarni FAQAT vositalar qaytargan
   chat_url qiymatidan oling va markdown körinişida yozing:
   [Ism1 ↔ Ism2](chat_url)
4. Javob tuzilişi:
   - Avval 1-2 gaplik xulosa (kim, kim bilan, qaçon, neçta xabar).
   - Keyin kerak bölsa qisqa röyxat yoki iqtiboslar (2-3 ta yetarli).
   - Oxirida "Suhbatni oçiş:" qismida tegişli havola(lar).
5. Xabar matnlarini töliq köpaytirmang — qisqa iqtibos keltiring. Şaxsiy ma'lumotlarni
   (telefon, parol kabi) qayta yozmang, faqat mavjudligini ayting.
6. 🗑 yoki "[öchirilgan]" belgisi — foydalanuvçi xabarni ÖÇIRGAN, lekin u admin
   monitoringida saqlanadi. Bunday xabarni zikr qilganda öçirilganini albatta ayting.
7. Heç narsa topilmasa, buni oçiq ayting va boşqa davr/kalit söz taklif qiling.
8. Qisqa, rasmiy-döstona ohang. Admin investigatsiya qilyapti — faktlar muhim.
"""


def _run_openai_agent(client, question, history=None):
    """Function-calling agent sikli. Natija: {'answer', 'links', 'mode', 'tools_used'}."""
    messages = [{"role": "system", "content": _system_prompt()}]

    # Oldingi savol-javoblar (kontekst) — oxirgi 4 ta buriliş
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
            # OpenAI SDK xatoligi sörov URL i, model va taşkilot ID sini
            # öz içiga oladi — brauzerga çiqarilmasin.
            from .security import safe_error
            return {
                'answer': "⚠️ " + safe_error(
                    e, 'chat_ai_openai', "AI xizmatiga ulanişda xatolik. Keyinroq urinib köring.",
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
        'answer': "⚠️ Agent juda köp qadam bajardi — savolni soddaroq qilib qayta yozing.",
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
#  Offline fallback (API kalit bölmasa) — oddiy qoidaviy tahlilçi
# ---------------------------------------------------------------------------
_QUESTION_WORDS = {
    'kimlar', 'kim', 'kimning', 'kimga', 'kimdan', 'bilan', 'nima', 'nimalar',
    'nimalarni', 'nimani', 'haqida', 'haqidagi', 'mavzu', 'mavzusida', 'mavzuda',
    'mavzusidagi', "töğrisida", "töğrisidagi", 'gaplaşibdi', 'gaplaşgan',
    'gaplaşganmi', 'yozişdi', 'yozişgan', 'yozişganmi', 'yozişyapti',
    'yozişmalar', 'yozişma', 'yozgan', 'yozgandir', 'suhbatlaşdi', 'suhbat',
    'suhbatlar', 'suhbatdoş', 'çatda', 'çat', 'çatlar', 'xabar', 'xabarlar',
    'bugun', 'keça', 'qaçon', 'qayerda', 'bormi', "böldi", "böldimi",
    "bölgan", "bölganmi", "söz", "sözi", "sözida", 'mavjudmi', 'mavjud',
    'deb', 'qanday', 'qaysi', 'qandaydir', 'iltimos', 'ayting', 'aytingçi',
    'koring', "köring", "körib", "körsating", 'çiqib', 'çiqarib', 'toping',
    'topib', 'şu', 'uşbu', 'şunda', 'şunday', 'men', 'menga', 'sorayman',
    "sörayman", "sörasiz", 'neçta', 'neççi', 'qança', 'barça', 'hamma',
    'hammasi', 'eng', 'faol', 'orqali', 'uçun', 'haqidagi', 'bor', "yöq",
    "yöqmi", 'emas', 'edi', 'ekan', 'kan', 'mikan', 'mikin', 'chunki',
}


def _fallback_period(q):
    today = timezone.localdate()
    if 'keça' in q:
        return today - timedelta(days=1), today - timedelta(days=1)
    if 'bugun' in q or 'hozir' in q:
        return today, today
    if 'hafta' in q:
        return today - timedelta(days=7), today
    if 'oyda' in q or 'şu oy' in q or "bir oy" in q:
        return today - timedelta(days=30), today
    return None, None


def _fallback_keywords(question):
    tokens = re.findall(r"[A-Za-zÀ-ž0-9'ʼ’\-]+", question.lower())
    words = [t for t in tokens if len(t) >= 3 and to_new_alphabet(t) not in _QUESTION_WORDS]
    return words


def _run_fallback(question):
    q = to_new_alphabet(question.lower())
    d_from, d_to = _fallback_period(q)
    users = _find_users(question)
    links = []

    # 1) "X kimlar bilan yozişdi?" naqşi
    if users and any(w in q for w in ('kimlar bilan', 'kim bilan', 'yozişdi', 'yozişgan',
                                      'suhbatlaşdi', 'gaplaşdi', 'yozişyapti')):
        result_json, links = tool_get_user_partners(
            users[0].pk,
            d_from.isoformat() if d_from else None,
            d_to.isoformat() if d_to else None,
        )
        data = json.loads(result_json)
        partners = data.get('partners', [])
        period = data.get('period', '')
        period_in = 'jami' if period == 'barça vaqt' else period
        uname = users[0].full_name or users[0].username
        if not partners:
            answer = (f"**{uname}** {period_in} heç kim bilan şaxsiy yozişma qilmagan.\n\n"
                      f"Boşqa davrni sinab köring (masalan: *{uname} şu hafta kimlar bilan yozişdi?*).")
        else:
            lines = [f"**{uname}** {period_in} **{len(partners)}** kişi bilan yozişgan:\n"]
            for p in partners:
                lines.append(f"- [{p['partner']}]({p['chat_url']}) — **{p['messages']}** ta xabar "
                             f"(oxirgisi: {p['last_message_at']})")
            lines.append("\nSuhbatni oçiş uçun yuqoridagi havolani bosing.")
            answer = '\n'.join(lines)
        return {'answer': answer, 'links': _dedupe_links(links), 'mode': 'fallback',
                'tools_used': ['get_user_partners'], 'ok': True}

    # 2) "X nima haqida gaplaşgan?" — öşa odamning suhbatlari + namuna xabarlar
    if users and ('nima' in q or 'mavzu' in q or 'haqida' in q):
        result_json, links = tool_get_user_partners(
            users[0].pk,
            d_from.isoformat() if d_from else None,
            d_to.isoformat() if d_to else None,
        )
        data = json.loads(result_json)
        partners = data.get('partners', [])
        uname = users[0].full_name or users[0].username
        if not partners:
            answer = f"**{uname}** ning {data.get('period', '')} suhbatlari topilmadi."
        else:
            lines = [f"**{uname}**ning {data.get('period', '')} suhbatlari va namuna xabarlar:\n"]
            for p in partners:
                lines.append(f"**[{p['partner']}]({p['chat_url']})** — {p['messages']} ta xabar:")
                for s in p.get('sample_messages', [])[:2]:
                    lines.append(f"> {s}")
                lines.append('')
            answer = '\n'.join(lines)
        return {'answer': answer, 'links': _dedupe_links(links), 'mode': 'fallback',
                'tools_used': ['get_user_partners'], 'ok': True}

    # 3) "Eng faol suhbatlar" naqşi
    if ('eng' in q and 'faol' in q) or 'reyting' in q or 'top' in q:
        result_json, links = tool_get_top_conversations(
            d_from.isoformat() if d_from else None,
            d_to.isoformat() if d_to else None,
        )
        data = json.loads(result_json)
        top = data.get('top', [])
        period = data.get('period', '')
        if not top:
            answer = f"**{period.capitalize()}** faol suhbatlar topilmadi."
        else:
            lines = [f"**{period.capitalize()} eng faol suhbatlar:**\n"]
            for i, t in enumerate(top, 1):
                lines.append(f"{i}. [{t['pair']}]({t['chat_url']}) — **{t['messages']}** ta xabar")
            answer = '\n'.join(lines)
        return {'answer': answer, 'links': _dedupe_links(links), 'mode': 'fallback',
                'tools_used': ['get_top_conversations'], 'ok': True}

    # 4) Kalit söz böyiça qidiruv: "sevgi mavzusida kimlar gaplaşibdi?"
    keywords = _fallback_keywords(question)
    if keywords:
        keyword = ' '.join(keywords[:4])
        result_json, links = tool_search_messages(
            keyword,
            d_from.isoformat() if d_from else None,
            d_to.isoformat() if d_to else None,
        )
        data = json.loads(result_json)
        matches = data.get('matches', [])
        if not matches:
            answer = (f"**\"{keyword}\"** böyiça {data.get('period', '')} heç qanday xabar topilmadi.\n\n"
                      f"Boşqa kalit söz yoki davr bilan urinib köring.")
        else:
            # juftliklar böyiça guruhlaş
            by_pair = {}
            for m in matches:
                key = m['chat_url']
                by_pair.setdefault(key, {'label': f"{m['from']} ↔ {m['to']}", 'texts': []})
                by_pair[key]['texts'].append(f"> {m['from']}: {m['text']}  *( {m['at']} )*")
            lines = [f"**\"{keyword}\"** mavzusida **{len(by_pair)}** ta suhbatda yozişma topildi:\n"]
            for url, grp in by_pair.items():
                lines.append(f"**[{grp['label']}]({url})**")
                lines.extend(grp['texts'][:3])
                lines.append('')
            answer = '\n'.join(lines)
        return {'answer': answer, 'links': _dedupe_links(links), 'mode': 'fallback',
                'tools_used': ['search_messages'], 'ok': True}

    # 5) Faqat davr söralgan ("keça nima bölgan?") — öşa davr faolligi
    if d_from or d_to:
        result_json, links = tool_get_top_conversations(
            d_from.isoformat() if d_from else None,
            d_to.isoformat() if d_to else None,
        )
        data = json.loads(result_json)
        top = data.get('top', [])
        period = data.get('period', '')
        if not top:
            answer = f"**{period.capitalize()}** heç qanday yozişma bölmagan."
        else:
            lines = [f"**{period.capitalize()} yozişmalar faolligi:**\n"]
            for t in top:
                lines.append(f"- [{t['pair']}]({t['chat_url']}) — **{t['messages']}** ta xabar "
                             f"(oxirgisi: {t['last_message_at']})")
            lines.append("\nMavzuni biliş uçun masalan: *sevgi haqida kimlar gaplaşibdi?* deb sörang.")
            answer = '\n'.join(lines)
        return {'answer': answer, 'links': _dedupe_links(links), 'mode': 'fallback',
                'tools_used': ['get_top_conversations'], 'ok': True}

    # 6) Umumiy yordam
    answer = (
        "Savolingizni tuşunmadim. Quyidagiça sörang:\n"
        "- *Axmat kimlar bilan yozişdi bugun?*\n"
        "- *Sevgi mavzusida kimlar gaplaşibdi?*\n"
        "- *Bugun eng faol suhbatlar qaysi?*\n"
        "- *Madina nima haqida gaplaşgan şu hafta?*"
    )
    return {'answer': answer, 'links': [], 'mode': 'fallback', 'tools_used': [], 'ok': True}


# ---------------------------------------------------------------------------
#  Kiriş nuqtasi
# ---------------------------------------------------------------------------
def analyze_chats(question, history=None):
    """Admin savoliga javob qaytaradi.

    Qaytaradi: {'answer': markdown str, 'links': [{'url','label'}],
                'mode': 'openai'|'fallback', 'tools_used': [...], 'ok': bool}
    """
    question = (question or '').strip()
    if not question:
        return {'answer': "Savol böş.", 'links': [], 'mode': 'none', 'tools_used': [], 'ok': False}

    client = _get_client()
    if client:
        return _run_openai_agent(client, question, history)
    return _run_fallback(question)


def ai_available():
    """OpenAI kaliti sozlanganmi — UI'da badge körsatiş uçun."""
    return bool((getattr(settings, 'OPENAI_API_KEY', '') or '').strip())
