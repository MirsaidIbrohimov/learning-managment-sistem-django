"""
Bildirişnoma feed API — accounts/api/notify_views.py

Real-time bildirişnomalar polling orqali işlaydi (loyihada websocket yöq:
ASGI/Channels/Redis örnatilmagan, CACHES = LocMemCache). Çat API'ning
mavjud polling arxitekturasi şu yerda ham davom etadi.

  GET /accounts/api/notify/feed/?since=<epoch_ms>

`since` berilmasa — "backlog" rejimi: foydalanuvçi tizimga kirgan paytda
öqilmagan xabarlari borligini bir marta körsatiş uçun umumiy xulosa
qaytariladi. `since` berilsa — faqat şu vaqtdan keyin kelgan yangi
hodisalar qaytariladi (toast + ovoz uçun).
"""

from datetime import datetime, timedelta, timezone as dt_timezone

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.models import (
    Profession,
    CourseEnrollment,
    GroupChatMessage,
    GroupChatRead,
    DirectMessage,
    Message,
)

from .homework_views import _ok, rate_limited
from .chat_views import _is_admin

# Bir marta qaytariladigan maksimal hodisa soni — toast böroni bölmasligi uçun
MAX_ITEMS = 6
# `since` juda uzoq ötmişda bölsa (tab uxlab qolgan) şu çegaradan orqaga qaramaymiz
MAX_LOOKBACK_SECONDS = 60 * 60 * 6


def _preview(text, has_file, limit=90):
    text = (text or '').strip()
    if text:
        return text[:limit] + ('…' if len(text) > limit else '')
    return '📎 Fayl' if has_file else '…'


def _photo(obj, request):
    photo = getattr(obj, 'photo', None)
    if not photo:
        return None
    try:
        return request.build_absolute_uri(photo.url)
    except Exception:
        return None


def _safe_url(name, *args):
    try:
        return reverse(name, args=args) if args else reverse(name)
    except Exception:
        return '#'


def _my_professions(user):
    """Foydalanuvçi kira oladigan guruh çatlari (çat sidebar bilan bir xil mantiq)."""
    if _is_admin(user):
        qs = Profession.objects.all()
    elif getattr(user, 'is_teacher', False):
        qs = user.teaching_professions.all()
    else:
        qs = Profession.objects.filter(enrollments__user=user)
    return qs.distinct()


def _parse_since(raw):
    """Client yuborgan epoch-ms ni aware datetime'ga aylantiradi."""
    if not raw:
        return None
    try:
        ms = int(raw)
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    try:
        dt = datetime.fromtimestamp(ms / 1000.0, tz=dt_timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    floor = timezone.now() - timedelta(seconds=MAX_LOOKBACK_SECONDS)
    return max(dt, floor)


def _group_unread_map(user, professions):
    """{profession_id: öqilmagan guruh xabarlari soni}"""
    reads = {
        r.profession_id: r.last_read_at
        for r in GroupChatRead.objects.filter(user=user)
    }
    out = {}
    for prof in professions:
        qs = GroupChatMessage.objects.filter(
            profession=prof, is_deleted=False
        ).exclude(sender=user)
        last_read = reads.get(prof.pk)
        if last_read:
            qs = qs.filter(created_at__gt=last_read)
        n = qs.count()
        if n:
            out[prof.pk] = n
    return out


def _system_unread_qs(user):
    """Öqilmagan tizim xabarlari — navbar badge'i bilan bir xil mantiq
    (context_processors.unread_messages)."""
    broadcast_types = ['all']
    if getattr(user, 'is_student', False):
        broadcast_types.append('students')
    if getattr(user, 'is_teacher', False):
        broadcast_types.append('teachers')
    return Message.objects.filter(
        Q(recipient=user)
        | Q(recipient__isnull=True, message_type__in=broadcast_types),
        is_read=False,
    )


RECENT_PER_SECTION = 3


def _recent(user, request, professions):
    """Panel uçun: suhbatlar va xabarlardan oxirgi 3 tadan — faqat öqilmaganlari."""
    n = RECENT_PER_SECTION
    chats = []
    for m in (DirectMessage.objects
              .filter(recipient=user, is_deleted=False, is_read=False)
              .select_related('sender').order_by('-created_at', '-pk')[:n]):
        chats.append({
            'uid': f'dm-{m.pk}', 'kind': 'dm',
            'title': m.sender.full_name or m.sender.username,
            'body': _preview(m.message, bool(m.file)),
            'url': _safe_url('direct_chat', m.sender_id),
            'photo': _photo(m.sender, request),
            'initials': m.sender.get_initials() or '??',
            'ts': int(m.created_at.timestamp() * 1000),
        })
    if professions:
        reads = {r.profession_id: r.last_read_at for r in GroupChatRead.objects.filter(user=user)}
        unread_q = Q()
        for prof in professions:
            last_read = reads.get(prof.pk)
            unread_q |= Q(profession=prof, created_at__gt=last_read) if last_read else Q(profession=prof)
        for m in (GroupChatMessage.objects
                  .filter(unread_q, is_deleted=False)
                  .exclude(sender=user)
                  .select_related('sender', 'profession').order_by('-created_at', '-pk')[:n]):
            sender_name = (m.sender.full_name or m.sender.username) if m.sender_id else 'Tizim'
            chats.append({
                'uid': f'grp-{m.pk}', 'kind': 'group',
                'title': m.profession.name,
                'body': f"{sender_name}: {_preview(m.message, bool(m.file), 70)}",
                'url': _safe_url('group_chat', m.profession_id),
                'photo': _photo(m.profession, request),
                'initials': (m.profession.name or '?')[:2].upper(),
                'ts': int(m.created_at.timestamp() * 1000),
            })
    chats.sort(key=lambda x: (x['ts'], x['uid']), reverse=True)

    system = [{
        'uid': f'sys-{m.pk}', 'kind': 'system',
        'title': m.title or 'Bildirişnoma',
        'body': _preview(m.content, False),
        'url': _safe_url('message_detail', m.pk),
        'photo': None, 'initials': '🔔',
        'ts': int(m.created_at.timestamp() * 1000),
    } for m in _system_unread_qs(user).order_by('-created_at', '-pk')[:n]]
    return {'chats': chats[:n], 'messages': system}


@login_required
@require_http_methods(["POST"])
def notify_mark_all_read(request):
    """Qönğiroq panelidagi barça suhbat va xabarlarni öqilgan deb belgilaş."""
    user = request.user
    now = timezone.now()
    DirectMessage.objects.filter(recipient=user, is_read=False).update(is_read=True)
    for prof in _my_professions(user):
        GroupChatRead.objects.update_or_create(profession=prof, user=user, defaults={'last_read_at': now})
    # Xabarlar sahifasidagi "Barçasini öqilgan" bilan bir xil qoida.
    _system_unread_qs(user).update(is_read=True)
    return _ok({'counts': {'dm': 0, 'group': 0, 'system': 0, 'chat': 0, 'total': 0},
                'recent': {'chats': [], 'messages': []}})


@login_required
@rate_limited('notify_feed')
@require_http_methods(["GET"])
def notify_feed(request):
    user = request.user
    now = timezone.now()
    since = _parse_since(request.GET.get('since'))

    professions = list(_my_professions(user))

    # ── Hisoblagiçlar (badge'lar uçun) ──────────────────────────────
    dm_unread = DirectMessage.objects.filter(
        recipient=user, is_read=False, is_deleted=False
    ).count()
    group_unread_map = _group_unread_map(user, professions)
    group_unread = sum(group_unread_map.values())
    system_unread = _system_unread_qs(user).count()

    counts = {
        'dm': dm_unread,
        'group': group_unread,
        'system': system_unread,
        'chat': dm_unread + group_unread,
        'total': dm_unread + group_unread + system_unread,
    }

    payload = {
        'now': int(now.timestamp() * 1000),
        'counts': counts,
        'items': [],
        'backlog': None,
        'recent': _recent(user, request, professions),
    }

    # ── Backlog rejimi: login qilgandan keyingi birinçi sörov ───────
    if since is None:
        if counts['total']:
            lines = []
            if dm_unread:
                senders = list(
                    DirectMessage.objects.filter(
                        recipient=user, is_read=False, is_deleted=False
                    ).select_related('sender')
                    .values('sender__first_name', 'sender__last_name', 'sender__username')
                    .annotate(n=Count('id')).order_by('-n')[:3]
                )
                names = []
                for s in senders:
                    full = f"{s['sender__first_name'] or ''} {s['sender__last_name'] or ''}".strip()
                    names.append(full or s['sender__username'])
                lines.append(f"💬 {dm_unread} şaxsiy xabar — {', '.join(names)}")
            if group_unread:
                lines.append(f"👥 {group_unread} guruh xabari")
            if system_unread:
                lines.append(f"🔔 {system_unread} tizim bildirişnomasi")
            payload['backlog'] = {
                'total': counts['total'],
                'lines': lines,
                'url': _safe_url('chat_inbox') if counts['chat'] else _safe_url('messages'),
            }
        return _ok(payload)

    # ── Yangi hodisalar (since'dan keyin) ─────────────────────────────
    items = []

    for m in (DirectMessage.objects
              .filter(recipient=user, is_deleted=False, is_read=False,
                      created_at__gt=since)
              .select_related('sender')
              .order_by('-created_at')[:MAX_ITEMS]):
        items.append({
            'uid': f'dm-{m.pk}',
            'kind': 'dm',
            'title': m.sender.full_name or m.sender.username,
            'body': _preview(m.message, bool(m.file)),
            'url': _safe_url('direct_chat', m.sender_id),
            'photo': _photo(m.sender, request),
            'initials': m.sender.get_initials() or '??',
            'ts': int(m.created_at.timestamp() * 1000),
        })

    if professions:
        for m in (GroupChatMessage.objects
                  .filter(profession__in=professions, is_deleted=False,
                          created_at__gt=since)
                  .exclude(sender=user)
                  .select_related('sender', 'profession')
                  .order_by('-created_at')[:MAX_ITEMS]):
            sender_name = m.sender.full_name or m.sender.username if m.sender_id else 'Tizim'
            items.append({
                'uid': f'grp-{m.pk}',
                'kind': 'group',
                'title': m.profession.name,
                'body': f"{sender_name}: {_preview(m.message, bool(m.file), 70)}",
                'url': _safe_url('group_chat', m.profession_id),
                'photo': _photo(m.profession, request),
                'initials': (m.profession.name or '?')[:2].upper(),
                'ts': int(m.created_at.timestamp() * 1000),
            })

    for m in (_system_unread_qs(user)
              .filter(created_at__gt=since)
              .order_by('-created_at')[:MAX_ITEMS]):
        items.append({
            'uid': f'sys-{m.pk}',
            'kind': 'system',
            'title': m.title or 'Bildirişnoma',
            'body': _preview(m.content, False),
            'url': _safe_url('message_detail', m.pk),
            'photo': None,
            'initials': '🔔',
            'ts': int(m.created_at.timestamp() * 1000),
        })

    items.sort(key=lambda x: x['ts'])
    payload['items'] = items[-MAX_ITEMS:]
    return _ok(payload)
