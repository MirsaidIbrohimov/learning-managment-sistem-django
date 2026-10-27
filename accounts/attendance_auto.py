"""O'quvchi saytga kirgan kuni guruh davomatiga avtomatik "keldi" belgisi.

ActivityMiddleware kuniga bir marta (sessiya bo'yicha) chaqiradi — yangi login
ham, ochiq sessiya bilan qaytib kelish ham hisoblanadi.

Qoidalar:
  * faqat bugun darsi bor faol guruhlar uchun (davomat guruhga bog'langan);
  * o'qituvchi allaqachon belgi qo'ygan bo'lsa — tegilmaydi; o'qituvchi
    keyinroq belgilasa, uning belgisi avtomatik belgining ustidan yoziladi;
  * bloklangan (to'lov qilmagan) o'quvchi belgilanmaydi.
"""
from django.utils import timezone

AUTO_NOTE = "Avtomatik: saytga kirdi"


def auto_mark_present(user, today=None):
    """Bugungi darslar uchun 'present' yozuvini yaratadi. Yaratilganlar sonini qaytaradi."""
    if getattr(user, 'role', None) != 'student' or getattr(user, 'is_blocked', False):
        return 0
    from accounts.models import StudentAttendance, StudyGroup

    today = today or timezone.localdate()
    weekday = today.isoweekday()  # 1 = Dushanba … 6 = Shanba (7 — yakshanba, dars yo'q)
    created = 0
    for group in StudyGroup.objects.filter(students=user, is_active=True):
        if not group.has_day(weekday):
            continue
        _, made = StudentAttendance.objects.get_or_create(
            group=group, student=user, date=today,
            defaults={'status': 'present', 'note': AUTO_NOTE},
        )
        created += int(made)
    return created
