"""
Chat REST API — accounts/api/chat_views.py

Polling-based chat (no websockets). Two chat types:

GROUP CHAT (per course/profession):
  GET  /accounts/api/chat/group/<profession_pk>/messages/?after=<id>
  POST /accounts/api/chat/group/<profession_pk>/send/

DIRECT CHAT (1:1 between two users):
  GET  /accounts/api/chat/direct/<user_pk>/messages/?after=<id>
  POST /accounts/api/chat/direct/<user_pk>/send/
  GET  /accounts/api/chat/conversations/        → inbox (recent threads)
  GET  /accounts/api/chat/unread/               → total unread count (navbar badge)

Security:
  • @login_required + CSRF on mutating requests
  • Per-user rate limiting (reused from homework_views)
  • File: extension whitelist + size cap (reused)
  • Text: dangerous HTML stripped (reused)
  • Group access: enrolled students + assigned teachers + admins only
"""

import os
import html
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect

from accounts.models import (
    CustomUser,
    Profession,
    CourseEnrollment,
    GroupChatMessage,
    GroupChatRead,
    DirectMessage,
    MessageReaction,
    ChatPin,
    ChatTypingStatus,
)
from telegram_bot.utils import notify_user

# Reuse the battle-tested helpers from the homework chat API
from .homework_views import (
    _ok, _err, rate_limited,
    _validate_file, _safe_filename, _sanitize_html,
)

MESSAGES_LIMIT = 200  # max messages returned per fetch


# ──────────────────────────────────────────────────────────────────────
# Permission helpers
# ──────────────────────────────────────────────────────────────────────
def _is_admin(user):
    return getattr(user, 'is_admin', False) or getattr(user, 'is_admin_or_assistant', False) or user.is_staff


def _can_access_group(user, profession):
    """Enrolled student OR assigned teacher OR admin."""
    if _is_admin(user):
        return True
    if profession.teachers.filter(pk=user.pk).exists():
        return True
    return CourseEnrollment.objects.filter(user=user, profession=profession).exists()


def _can_dm(user, other):
    """Who can start a private chat with `other`.
    Allowed: anyone authenticated may message teachers/admins, and members of
    a shared course may message each other. Admins/teachers may message anyone."""
    if user.pk == other.pk:
        return False
    if _is_admin(user) or user.is_teacher:
        return True
    if other.is_teacher or getattr(other, 'is_admin', False):
        return True
    # shared course?
    my_courses = set(CourseEnrollment.objects.filter(user=user).values_list('profession_id', flat=True))
    if my_courses:
        their_courses = set(CourseEnrollment.objects.filter(user=other).values_list('profession_id', flat=True))
        if my_courses & their_courses:
            return True
    return False


def _notify_dm_telegram(recipient, sender, text, has_file):
    """Shaxsiy (1:1) chatga yangi xabar kelganda, agar qabul qiluvchi
    Telegram botga ulangan bo'lsa — unga bildirishnoma yuboradi."""
    if not recipient.telegram_id:
        return
    preview = html.escape(text[:150], quote=False) if text else "📎 Fayl yubordi"
    notify_user(
        recipient.telegram_id,
        f"💬 <b>Sizga yangi xabar bor!</b>\n\n"
        f"👤 {html.escape(sender.full_name or sender.username, quote=False)}\n"
        f"💭 {preview}"
    )


def _notify_group_telegram(profession, sender, text, has_file):
    """Guruh (kurs) chatiga yangi xabar kelganda — biriktirilgan o'qituvchilar
    va yozilgan o'quvchilardan Telegram botga ulangan barchasiga (yuboruvchidan
    boshqa) bildirishnoma yuboradi."""
    teacher_ids = set(
        profession.teachers.exclude(pk=sender.pk)
        .exclude(telegram_id__isnull=True)
        .values_list('pk', flat=True)
    )
    student_ids = set(
        CourseEnrollment.objects.filter(profession=profession)
        .exclude(user__pk=sender.pk)
        .exclude(user__telegram_id__isnull=True)
        .values_list('user_id', flat=True)
    )
    recipient_ids = teacher_ids | student_ids
    if not recipient_ids:
        return

    recipients = CustomUser.objects.filter(
        pk__in=recipient_ids, telegram_id__isnull=False, is_blocked=False
    ).values_list('telegram_id', flat=True)

    course_name = html.escape(profession.name or '', quote=False)
    sender_name = html.escape(sender.full_name or sender.username, quote=False)
    if text:
        preview = html.escape(text[:200], quote=False)
        if len(text) > 200:
            preview += '…'
    else:
        preview = "📎 Fayl yubordi" if has_file else ""

    body = (
        f"👥 <b>Guruh chatda yangi xabar</b>\n\n"
        f"📚 Kurs: <b>{course_name}</b>\n"
        f"👤 {sender_name}\n"
        f"💭 {preview}"
    )

    for tg_id in recipients:
        notify_user(tg_id, body)


# ──────────────────────────────────────────────────────────────────────
# Serializers
# ──────────────────────────────────────────────────────────────────────
def _user_brief(u, request):
    photo = None
    if getattr(u, 'photo', None):
        try:
            photo = request.build_absolute_uri(u.photo.url)
        except Exception:
            photo = None
    return {
        'id': u.pk,
        'name': u.full_name or u.username,
        'username': u.username,
        'photo': photo,
        'initials': u.get_initials(),
        'role': u.role,
        'is_online': u.is_online,
        'sub': _online_sub(u),
    }


def _file_url(obj, request):
    if obj.file:
        try:
            return request.build_absolute_uri(obj.file.url)
        except Exception:
            return None
    return None


def _reply_preview(msg):
    """Short preview of the message being replied to (Telegram-style quote)."""
    rt = msg.reply_to
    if not rt:
        return None
    return {
        'id': rt.pk,
        'sender_name': rt.sender.full_name or rt.sender.username,
        'snippet': (rt.message[:80] if rt.message else ('📎 Fayl' if rt.file else '')),
    }


def _serialize_reactions(msg, request):
    """Group reactions by emoji: [{emoji, count, mine}]. Relies on `.reactions`
    being prefetched by the caller's queryset to avoid N+1 on list views."""
    agg = {}
    mine = None
    for r in msg.reactions.all():
        agg[r.emoji] = agg.get(r.emoji, 0) + 1
        if r.user_id == request.user.pk:
            mine = r.emoji
    return [{'emoji': e, 'count': c, 'mine': e == mine} for e, c in agg.items()]


def _serialize_group_msg(msg, request):
    return {
        'id': msg.pk,
        'sender': _user_brief(msg.sender, request),
        'is_me': msg.sender_id == request.user.pk,
        'message': msg.message,
        'file_url': _file_url(msg, request),
        'file_name': os.path.basename(msg.file.name) if msg.file else None,
        'created_at': timezone.localtime(msg.created_at).strftime('%d.%m.%Y %H:%M'),
        'ts': msg.created_at.timestamp(),
        'reply_to': _reply_preview(msg),
        'is_edited': msg.is_edited,
        'is_forwarded': msg.is_forwarded,
        'forwarded_from': msg.forwarded_sender_name,
        'reactions': _serialize_reactions(msg, request),
    }


def _serialize_dm(msg, request):
    return {
        'id': msg.pk,
        'sender_id': msg.sender_id,
        'is_me': msg.sender_id == request.user.pk,
        'message': msg.message,
        'file_url': _file_url(msg, request),
        'file_name': os.path.basename(msg.file.name) if msg.file else None,
        'created_at': timezone.localtime(msg.created_at).strftime('%d.%m.%Y %H:%M'),
        'ts': msg.created_at.timestamp(),
        'is_read': msg.is_read,
        'is_delivered': msg.is_delivered,
        'reply_to': _reply_preview(msg),
        'is_edited': msg.is_edited,
        'is_forwarded': msg.is_forwarded,
        'forwarded_from': msg.forwarded_sender_name,
        'reactions': _serialize_reactions(msg, request),
    }


# ──────────────────────────────────────────────────────────────────────
# GROUP CHAT
# ──────────────────────────────────────────────────────────────────────
@login_required
@rate_limited('chat_group_list')
@require_http_methods(["GET"])
def group_messages(request, profession_pk):
    profession = get_object_or_404(Profession, pk=profession_pk)
    if not _can_access_group(request.user, profession):
        return _err("Bu guruh chatiga ruxsatingiz yo'q", 403)

    qs = GroupChatMessage.objects.filter(
        profession=profession, is_deleted=False
    ).select_related('sender', 'reply_to__sender').prefetch_related('reactions')

    after = request.GET.get('after')
    if after and after.isdigit():
        qs = qs.filter(pk__gt=int(after))
        msgs = list(qs.order_by('created_at')[:MESSAGES_LIMIT])
    else:
        # latest page, returned in chronological order
        msgs = list(qs.order_by('-created_at')[:MESSAGES_LIMIT])
        msgs.reverse()

    # update read state
    GroupChatRead.objects.update_or_create(
        profession=profession, user=request.user,
        defaults={'last_read_at': timezone.now()},
    )

    return _ok({
        'messages': [_serialize_group_msg(m, request) for m in msgs],
        'group': {'id': profession.pk, 'name': profession.name},
    })


_ROLE_LABELS = {
    'admin': 'Admin',
    'assistant_admin': 'Admin',
    'teacher': "O'qituvchi",
    'student': "O'quvchi",
}


@login_required
@rate_limited('chat_group_list')
@require_http_methods(["GET"])
def group_members(request, profession_pk):
    """Guruh (kurs) a'zolari: biriktirilgan o'qituvchilar + yozilgan o'quvchilar.
    O'ng paneldagi 'A'zolar' ro'yxati uchun ishlatiladi."""
    profession = get_object_or_404(Profession, pk=profession_pk)
    if not _can_access_group(request.user, profession):
        return _err("Bu guruh chatiga ruxsatingiz yo'q", 403)

    seen = set()
    members = []

    def _add(u):
        if not u or u.pk in seen:
            return
        seen.add(u.pk)
        brief = _user_brief(u, request)
        brief['role_label'] = _ROLE_LABELS.get(u.role, u.role or '')
        members.append(brief)

    # O'qituvchilar avval
    for t in profession.teachers.all():
        _add(t)
    # Keyin yozilgan o'quvchilar
    enrollments = (
        CourseEnrollment.objects
        .filter(profession=profession)
        .select_related('user')
    )
    for e in enrollments:
        _add(e.user)

    # Tartib: avval rol (admin/o'qituvchi yuqorida), keyin online, keyin ism
    role_rank = {'admin': 0, 'assistant_admin': 0, 'teacher': 1, 'student': 2}
    members.sort(key=lambda m: (
        role_rank.get(m.get('role'), 3),
        0 if m.get('is_online') else 1,
        (m.get('name') or '').lower(),
    ))

    online_count = sum(1 for m in members if m.get('is_online'))
    return _ok({
        'group': {
            'id': profession.pk,
            'name': profession.name,
            'members_count': len(members),
            'online_count': online_count,
        },
        'members': members,
    })


@login_required
@csrf_protect
@rate_limited('chat_group_send')
@require_http_methods(["POST"])
def group_send(request, profession_pk):
    profession = get_object_or_404(Profession, pk=profession_pk)
    if not _can_access_group(request.user, profession):
        return _err("Bu guruh chatiga ruxsatingiz yo'q", 403)

    text = (request.POST.get('message') or '').strip()
    up_file = request.FILES.get('file')
    if not text and not up_file:
        return _err("Xabar yoki fayl yuboring")
    if len(text) > 5000:
        return _err("Xabar juda uzun (max 5000 belgi)")

    text = _sanitize_html(text) if text else ''
    if up_file:
        ok, err = _validate_file(up_file)
        if not ok:
            return _err(err)
        up_file.name = _safe_filename(up_file.name)

    reply_obj = None
    reply_id = request.POST.get('reply_to')
    if reply_id and str(reply_id).isdigit():
        reply_obj = GroupChatMessage.objects.filter(
            pk=reply_id, profession=profession, is_deleted=False
        ).first()

    msg = GroupChatMessage.objects.create(
        profession=profession, sender=request.user,
        message=text, file=up_file if up_file else None,
        reply_to=reply_obj,
    )
    _notify_group_telegram(profession, request.user, text, bool(up_file))
    return _ok({'message': _serialize_group_msg(msg, request)})


# ──────────────────────────────────────────────────────────────────────
# DIRECT CHAT
# ──────────────────────────────────────────────────────────────────────
def _dm_thread_qs(a, b):
    return DirectMessage.objects.filter(
        Q(sender=a, recipient=b) | Q(sender=b, recipient=a),
        is_deleted=False,
    )


@login_required
@rate_limited('chat_dm_list')
@require_http_methods(["GET"])
def direct_messages(request, user_pk):
    other = get_object_or_404(CustomUser, pk=user_pk)
    if other.pk == request.user.pk:
        return _err("O'zingizga yozolmaysiz", 400)

    qs = _dm_thread_qs(request.user, other).select_related(
        'reply_to__sender'
    ).prefetch_related('reactions')

    after = request.GET.get('after')
    if after and after.isdigit():
        qs = qs.filter(pk__gt=int(after))
        msgs = list(qs.order_by('created_at')[:MESSAGES_LIMIT])
    else:
        msgs = list(qs.order_by('-created_at')[:MESSAGES_LIMIT])
        msgs.reverse()

    # mark received messages as delivered (this poll = client has them) + read
    _dm_thread_qs(request.user, other).filter(
        recipient=request.user, is_delivered=False
    ).update(is_delivered=True, delivered_at=timezone.now())
    _dm_thread_qs(request.user, other).filter(
        recipient=request.user, is_read=False
    ).update(is_read=True)

    return _ok({
        'messages': [_serialize_dm(m, request) for m in msgs],
        'partner': _user_brief(other, request),
    })


@login_required
@csrf_protect
@rate_limited('chat_dm_send')
@require_http_methods(["POST"])
def direct_send(request, user_pk):
    other = get_object_or_404(CustomUser, pk=user_pk)
    if not _can_dm(request.user, other):
        return _err("Bu foydalanuvchiga xabar yozolmaysiz", 403)

    text = (request.POST.get('message') or '').strip()
    up_file = request.FILES.get('file')
    if not text and not up_file:
        return _err("Xabar yoki fayl yuboring")
    if len(text) > 5000:
        return _err("Xabar juda uzun (max 5000 belgi)")

    text = _sanitize_html(text) if text else ''
    if up_file:
        ok, err = _validate_file(up_file)
        if not ok:
            return _err(err)
        up_file.name = _safe_filename(up_file.name)

    reply_obj = None
    reply_id = request.POST.get('reply_to')
    if reply_id and str(reply_id).isdigit():
        reply_obj = _dm_thread_qs(request.user, other).filter(pk=reply_id).first()

    msg = DirectMessage.objects.create(
        sender=request.user, recipient=other,
        message=text, file=up_file if up_file else None,
        reply_to=reply_obj,
    )
    _notify_dm_telegram(other, request.user, text, bool(up_file))
    return _ok({'message': _serialize_dm(msg, request)})


@login_required
@rate_limited('chat_conversations')
@require_http_methods(["GET"])
def conversations(request):
    """Inbox: recent direct-message threads with last message + unread count."""
    me = request.user
    msgs = DirectMessage.objects.filter(
        Q(sender=me) | Q(recipient=me), is_deleted=False
    ).select_related('sender', 'recipient').order_by('-created_at')

    threads = {}
    for m in msgs:
        partner = m.recipient if m.sender_id == me.pk else m.sender
        if partner.pk in threads:
            continue  # already have the latest for this partner
        threads[partner.pk] = {
            'partner': _user_brief(partner, request),
            'last_message': (m.message[:60] or ('📎 Fayl' if m.file else '')),
            'last_at': timezone.localtime(m.created_at).strftime('%d.%m.%Y %H:%M'),
            'ts': m.created_at.timestamp(),
            'is_mine': m.sender_id == me.pk,
            'unread': 0,
        }

    # unread counts per partner
    unread_counts = (DirectMessage.objects
                     .filter(recipient=me, is_read=False, is_deleted=False)
                     .values('sender').annotate(n=Count('id')))
    for row in unread_counts:
        if row['sender'] in threads:
            threads[row['sender']]['unread'] = row['n']

    result = sorted(threads.values(), key=lambda t: t['ts'], reverse=True)
    return _ok({'conversations': result})


@login_required
@rate_limited('chat_unread')
@require_http_methods(["GET"])
def unread_count(request):
    """Total unread direct messages (for navbar badge)."""
    n = DirectMessage.objects.filter(
        recipient=request.user, is_read=False, is_deleted=False
    ).count()
    return _ok({'unread': n})


# ──────────────────────────────────────────────────────────────────────
# Per-message actions: edit / delete / react / forward
# (kind = 'dm' | 'group' — message PKs are not unique across the two
# tables, so every per-message endpoint is dispatched through `kind`.)
# ──────────────────────────────────────────────────────────────────────
_KIND_MODELS = {'dm': DirectMessage, 'group': GroupChatMessage}


def _get_message(kind, msg_id):
    """Returns (model, msg) for a non-deleted message, or (None, None) if
    `kind` is invalid, or (model, None) if the message doesn't exist."""
    model = _KIND_MODELS.get(kind)
    if not model:
        return None, None
    related = ['sender', 'recipient'] if kind == 'dm' else ['sender', 'profession']
    msg = model.objects.filter(pk=msg_id, is_deleted=False).select_related(*related).first()
    return model, msg


def _can_view_message(user, kind, msg):
    if kind == 'dm':
        return user.pk in (msg.sender_id, msg.recipient_id)
    return _can_access_group(user, msg.profession)


def _can_delete_message(user, kind, msg):
    if msg.sender_id == user.pk or _is_admin(user):
        return True
    if kind == 'group':
        return msg.profession.teachers.filter(pk=user.pk).exists()
    return False


@login_required
@csrf_protect
@rate_limited('chat_msg_edit')
@require_http_methods(["POST"])
def message_edit(request, kind, msg_id):
    model, msg = _get_message(kind, msg_id)
    if not model:
        return _err("Noto'g'ri so'rov", 400)
    if not msg:
        return _err("Xabar topilmadi", 404)
    if msg.sender_id != request.user.pk:
        return _err("Faqat o'z xabaringizni tahrirlay olasiz", 403)

    text = (request.POST.get('message') or '').strip()
    if not text:
        return _err("Xabar matni bo'sh bo'lishi mumkin emas")
    if len(text) > 5000:
        return _err("Xabar juda uzun (max 5000 belgi)")

    new_text = _sanitize_html(text)
    # Shaxsiy xabarlar uchun tahrir tarixini saqlaymiz — admin panel
    # investigatsiyasida asl matn ko'rinib turishi kerak.
    if kind == 'dm' and msg.message != new_text:
        from accounts.models import DirectMessageEditHistory
        DirectMessageEditHistory.objects.create(message=msg, old_text=msg.message)

    msg.message = new_text
    msg.is_edited = True
    msg.edited_at = timezone.now()
    msg.save(update_fields=['message', 'is_edited', 'edited_at'])

    serialize = _serialize_dm if kind == 'dm' else _serialize_group_msg
    return _ok({'message': serialize(msg, request)})


@login_required
@csrf_protect
@rate_limited('chat_msg_delete')
@require_http_methods(["POST"])
def message_delete(request, kind, msg_id):
    model, msg = _get_message(kind, msg_id)
    if not model:
        return _err("Noto'g'ri so'rov", 400)
    if not msg:
        return _err("Xabar topilmadi", 404)
    if not _can_delete_message(request.user, kind, msg):
        return _err("Bu xabarni o'chirish huquqingiz yo'q", 403)

    msg.is_deleted = True
    update = ['is_deleted']
    if kind == 'dm':
        msg.deleted_at = timezone.now()
        update.append('deleted_at')
    msg.save(update_fields=update)
    return _ok({'id': msg.pk})


@login_required
@csrf_protect
@rate_limited('chat_msg_react')
@require_http_methods(["POST"])
def message_react(request, kind, msg_id):
    model, msg = _get_message(kind, msg_id)
    if not model:
        return _err("Noto'g'ri so'rov", 400)
    if not msg:
        return _err("Xabar topilmadi", 404)
    if not _can_view_message(request.user, kind, msg):
        return _err("Ruxsat yo'q", 403)

    emoji = (request.POST.get('emoji') or '').strip()
    valid_emojis = {choice[0] for choice in MessageReaction.EMOJI_CHOICES}
    if emoji not in valid_emojis:
        return _err("Noto'g'ri emoji")

    field = 'direct_message' if kind == 'dm' else 'group_message'
    existing = MessageReaction.objects.filter(user=request.user, **{field: msg}).first()
    if existing and existing.emoji == emoji:
        existing.delete()  # tap same emoji again → remove reaction
    elif existing:
        existing.emoji = emoji
        existing.save(update_fields=['emoji'])
    else:
        MessageReaction.objects.create(user=request.user, emoji=emoji, **{field: msg})

    return _ok({'reactions': _serialize_reactions(msg, request)})


@login_required
@csrf_protect
@rate_limited('chat_msg_forward')
@require_http_methods(["POST"])
def message_forward(request, kind, msg_id):
    model, msg = _get_message(kind, msg_id)
    if not model:
        return _err("Noto'g'ri so'rov", 400)
    if not msg:
        return _err("Xabar topilmadi", 404)
    if not _can_view_message(request.user, kind, msg):
        return _err("Ruxsat yo'q", 403)

    to_kind = request.POST.get('to_kind')
    to_id = request.POST.get('to_id')
    if to_kind not in ('dm', 'group') or not (to_id or '').isdigit():
        return _err("Qabul qiluvchi noto'g'ri")
    to_id = int(to_id)

    original_sender_name = msg.sender.full_name or msg.sender.username

    if to_kind == 'dm':
        target_user = get_object_or_404(CustomUser, pk=to_id)
        if not _can_dm(request.user, target_user):
            return _err("Bu foydalanuvchiga forward qilolmaysiz", 403)
        new_msg = DirectMessage.objects.create(
            sender=request.user, recipient=target_user,
            message=msg.message, file=msg.file or None,
            is_forwarded=True, forwarded_sender_name=original_sender_name,
        )
        _notify_dm_telegram(target_user, request.user, msg.message, bool(msg.file))
        return _ok({'message': _serialize_dm(new_msg, request)})

    target_group = get_object_or_404(Profession, pk=to_id)
    if not _can_access_group(request.user, target_group):
        return _err("Bu guruhga forward qilolmaysiz", 403)
    new_msg = GroupChatMessage.objects.create(
        profession=target_group, sender=request.user,
        message=msg.message, file=msg.file or None,
        is_forwarded=True, forwarded_sender_name=original_sender_name,
    )
    _notify_group_telegram(target_group, request.user, msg.message, bool(msg.file))
    return _ok({'message': _serialize_group_msg(new_msg, request)})


# ──────────────────────────────────────────────────────────────────────
# Typing indicator (DB-backed — works across multiple Passenger workers,
# unlike per-process LocMemCache). Frontend pings every ~4s while typing;
# a status row older than TYPING_TTL_SECONDS is treated as "not typing".
# ──────────────────────────────────────────────────────────────────────
TYPING_TTL_SECONDS = 6


@login_required
@rate_limited('chat_typing')
@require_http_methods(["POST"])
def typing_ping(request):
    kind = request.POST.get('kind')
    target_id = request.POST.get('target_id')
    if kind not in ('dm', 'group') or not (target_id or '').isdigit():
        return _err("Noto'g'ri so'rov", 400)
    target_id = int(target_id)

    if kind == 'dm':
        other = get_object_or_404(CustomUser, pk=target_id)
        if not _can_dm(request.user, other):
            return _err("Ruxsat yo'q", 403)
        ChatTypingStatus.objects.update_or_create(
            user=request.user, partner=other, profession=None,
        )
    else:
        profession = get_object_or_404(Profession, pk=target_id)
        if not _can_access_group(request.user, profession):
            return _err("Ruxsat yo'q", 403)
        ChatTypingStatus.objects.update_or_create(
            user=request.user, partner=None, profession=profession,
        )
    return _ok()


@login_required
@rate_limited('chat_typing_status')
@require_http_methods(["GET"])
def typing_status(request):
    kind = request.GET.get('kind')
    target_id = request.GET.get('target_id')
    if kind not in ('dm', 'group') or not (target_id or '').isdigit():
        return _err("Noto'g'ri so'rov", 400)
    target_id = int(target_id)
    cutoff = timezone.now() - timedelta(seconds=TYPING_TTL_SECONDS)

    if kind == 'dm':
        get_object_or_404(CustomUser, pk=target_id)
        is_typing = ChatTypingStatus.objects.filter(
            user_id=target_id, partner_id=request.user.pk, updated_at__gte=cutoff
        ).exists()
        return _ok({'typing': is_typing})

    profession = get_object_or_404(Profession, pk=target_id)
    if not _can_access_group(request.user, profession):
        return _err("Ruxsat yo'q", 403)
    rows = (ChatTypingStatus.objects
            .filter(profession=profession, updated_at__gte=cutoff)
            .exclude(user_id=request.user.pk)
            .select_related('user')
            .values_list('user__first_name', 'user__last_name'))
    typing_users = [f"{f} {l}".strip() for f, l in rows if (f or l)]
    return _ok({'typing_users': typing_users})


# ──────────────────────────────────────────────────────────────────────
# Pin a conversation (shown first in the sidebar)
# ──────────────────────────────────────────────────────────────────────
@login_required
@csrf_protect
@rate_limited('chat_pin')
@require_http_methods(["POST"])
def pin_toggle(request):
    kind = request.POST.get('kind')
    target_id = request.POST.get('target_id')
    if kind not in ('dm', 'group') or not (target_id or '').isdigit():
        return _err("Noto'g'ri so'rov", 400)
    target_id = int(target_id)

    if kind == 'dm':
        other = get_object_or_404(CustomUser, pk=target_id)
        existing = ChatPin.objects.filter(user=request.user, partner=other).first()
        if existing:
            existing.delete()
            return _ok({'pinned': False})
        ChatPin.objects.create(user=request.user, partner=other)
        return _ok({'pinned': True})

    profession = get_object_or_404(Profession, pk=target_id)
    if not _can_access_group(request.user, profession):
        return _err("Ruxsat yo'q", 403)
    existing = ChatPin.objects.filter(user=request.user, profession=profession).first()
    if existing:
        existing.delete()
        return _ok({'pinned': False})
    ChatPin.objects.create(user=request.user, profession=profession)
    return _ok({'pinned': True})


# ──────────────────────────────────────────────────────────────────────
# User search (sidebar "new message" — name / username / email)
# ──────────────────────────────────────────────────────────────────────
@login_required
@rate_limited('chat_user_search')
@require_http_methods(["GET"])
def user_search(request):
    q = (request.GET.get('q') or '').strip()
    if len(q) < 2:
        return _ok({'users': []})

    me = request.user
    if _is_admin(me) or me.is_teacher:
        candidates = CustomUser.objects.exclude(pk=me.pk)
    else:
        course_ids = list(CourseEnrollment.objects.filter(user=me).values_list('profession_id', flat=True))
        candidates = CustomUser.objects.filter(
            Q(role__in=['teacher', 'admin']) | Q(enrollments__profession_id__in=course_ids)
        ).exclude(pk=me.pk).distinct()

    candidates = candidates.filter(
        Q(first_name__icontains=q) | Q(last_name__icontains=q) |
        Q(username__icontains=q) | Q(email__icontains=q)
    )[:20]

    results = [_user_brief(u, request) for u in candidates if _can_dm(me, u)]
    return _ok({'users': results})


# ──────────────────────────────────────────────────────────────────────
# Unified sidebar (Messenger-style page): merges direct + group threads
# into one pinned-first, recency-sorted list.
# ──────────────────────────────────────────────────────────────────────
_WEEKDAYS_UZ = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']


def _format_relative_time(dt):
    """Telegram-style relative time for sidebar rows: '14:32' (today),
    'Kecha' (yesterday), weekday name (this week), or 'dd.mm.yy' (older)."""
    local = timezone.localtime(dt)
    today = timezone.localtime(timezone.now()).date()
    delta_days = (today - local.date()).days
    if delta_days == 0:
        return local.strftime('%H:%M')
    if delta_days == 1:
        return 'Kecha'
    if delta_days < 7:
        return _WEEKDAYS_UZ[local.weekday()]
    return local.strftime('%d.%m.%y')


def _format_last_seen(dt):
    """Telegram-style 'oxirgi marta onlayn bo'lgan vaqt' matni:
    'hozirgina', '5 daqiqa oldin', 'bugun soat 14:32da',
    'kecha soat 09:10da', 'Dushanba kuni soat 18:00da' yoki 'dd.mm.yyyy'."""
    if not dt:
        return "hech qachon"
    local = timezone.localtime(dt)
    now = timezone.localtime(timezone.now())
    seconds = (now - local).total_seconds()
    if seconds < 60:
        return "hozirgina"
    if seconds < 3600:
        return f"{int(seconds // 60)} daqiqa oldin"
    delta_days = (now.date() - local.date()).days
    if delta_days == 0:
        return f"bugun soat {local.strftime('%H:%M')}da"
    if delta_days == 1:
        return f"kecha soat {local.strftime('%H:%M')}da"
    if delta_days < 7:
        return f"{_WEEKDAYS_UZ[local.weekday()]} kuni soat {local.strftime('%H:%M')}da"
    return local.strftime('%d.%m.%Y')


def _online_sub(user):
    """DM hamsuhbat uchun header/sidebar subtitle:
    'Online • @user' yoki 'Oxirgi faollik: ... • @user'."""
    status = 'Online' if user.is_online else f"Oxirgi faollik: {_format_last_seen(user.last_activity)}"
    return f"{status} • @{user.username}"


def _group_initials(name):
    parts = [p for p in (name or '').split() if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    if parts:
        return parts[0][:2].upper()
    return '??'


@login_required
@rate_limited('chat_sidebar')
@require_http_methods(["GET"])
def sidebar(request):
    """Combined conversation list (direct + group) for the unified chat page."""
    me = request.user
    items = []

    # ---- direct threads ----
    dm_msgs = (DirectMessage.objects
               .filter(Q(sender=me) | Q(recipient=me), is_deleted=False)
               .select_related('sender', 'recipient')
               .order_by('-created_at'))
    seen_partners = set()
    for m in dm_msgs:
        partner = m.recipient if m.sender_id == me.pk else m.sender
        if partner.pk in seen_partners:
            continue
        seen_partners.add(partner.pk)
        photo = None
        if getattr(partner, 'photo', None):
            try:
                photo = request.build_absolute_uri(partner.photo.url)
            except Exception:
                photo = None
        items.append({
            'kind': 'dm',
            'id': partner.pk,
            'name': partner.full_name or partner.username,
            'photo': photo,
            'initials': partner.get_initials(),
            'is_online': partner.is_online,
            'sub': _online_sub(partner),
            'last_message': (m.message[:60] if m.message else ('📎 Fayl' if m.file else '')),
            'is_mine_last': m.sender_id == me.pk,
            'last_at': _format_relative_time(m.created_at),
            'ts': m.created_at.timestamp(),
            'unread': 0,
            'pinned': False,
            'can_moderate': False,
        })

    unread_counts = dict(
        DirectMessage.objects.filter(recipient=me, is_read=False, is_deleted=False)
        .values('sender').annotate(n=Count('id')).values_list('sender', 'n')
    )
    for it in items:
        if it['kind'] == 'dm':
            it['unread'] = unread_counts.get(it['id'], 0)

    # ---- group threads ----
    if _is_admin(me):
        professions = Profession.objects.all()
    elif me.is_teacher:
        professions = me.teaching_professions.all()
    else:
        professions = Profession.objects.filter(enrollments__user=me)
    professions = professions.distinct()

    reads = {r.profession_id: r.last_read_at for r in GroupChatRead.objects.filter(user=me)}
    member_counts = dict(
        CourseEnrollment.objects.filter(profession__in=professions)
        .values('profession').annotate(n=Count('id')).values_list('profession', 'n')
    )
    teaching_ids = set(me.teaching_professions.values_list('pk', flat=True)) if not _is_admin(me) else set()
    for prof in professions:
        last_msg = (GroupChatMessage.objects
                    .filter(profession=prof, is_deleted=False)
                    .select_related('sender')
                    .order_by('-created_at').first())
        last_read = reads.get(prof.pk)
        unread_qs = GroupChatMessage.objects.filter(profession=prof, is_deleted=False).exclude(sender=me)
        unread = unread_qs.filter(created_at__gt=last_read).count() if last_read else unread_qs.count()
        photo = None
        if getattr(prof, 'photo', None):
            try:
                photo = request.build_absolute_uri(prof.photo.url)
            except Exception:
                photo = None
        items.append({
            'kind': 'group',
            'id': prof.pk,
            'name': prof.name,
            'photo': photo,
            'initials': _group_initials(prof.name),
            'is_online': None,
            'sub': f"{member_counts.get(prof.pk, 0)} a'zo",
            'last_message': (
                (('Siz: ' if last_msg.sender_id == me.pk else '') +
                 (last_msg.message[:60] if last_msg.message else ('📎 Fayl' if last_msg.file else '')))
                if last_msg else "Hali xabar yo'q"
            ),
            'is_mine_last': bool(last_msg and last_msg.sender_id == me.pk),
            'last_at': _format_relative_time(last_msg.created_at) if last_msg else '',
            'ts': last_msg.created_at.timestamp() if last_msg else 0,
            'unread': unread,
            'pinned': False,
            'can_moderate': _is_admin(me) or prof.pk in teaching_ids,
        })

    # ---- pins ----
    pins = ChatPin.objects.filter(user=me)
    pinned_dm_ids = {p.partner_id for p in pins if p.partner_id}
    pinned_group_ids = {p.profession_id for p in pins if p.profession_id}
    for it in items:
        if it['kind'] == 'dm' and it['id'] in pinned_dm_ids:
            it['pinned'] = True
        elif it['kind'] == 'group' and it['id'] in pinned_group_ids:
            it['pinned'] = True

    items.sort(key=lambda x: (not x['pinned'], -x['ts']))
    return _ok({'items': items})
