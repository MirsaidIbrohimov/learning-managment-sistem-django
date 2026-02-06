from __future__ import annotations

from django.db.models import Q


def unread_messages(request):
    """
    Navbar uchun o'qilmagan xabarlar soni.

    Eslatma:
    - Shaxsiy xabarlar: recipient=request.user
    - Umumiy xabarlar (agar ishlatilsa): recipient is NULL + message_type=all/students/teachers
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"unread_messages_count": 0}

    # Local import: app yuklanish paytida circular import bo'lmasin
    from .models import Message

    q = Q(recipient=user, is_read=False)
    # Umumiy xabarlar (agar bazada recipient NULL bo'lsa)
    q |= Q(recipient__isnull=True, message_type="all", is_read=False)
    if getattr(user, "is_student", False):
        q |= Q(recipient__isnull=True, message_type="students", is_read=False)
    if getattr(user, "is_teacher", False):
        q |= Q(recipient__isnull=True, message_type="teachers", is_read=False)

    return {"unread_messages_count": Message.objects.filter(q).distinct().count()}

