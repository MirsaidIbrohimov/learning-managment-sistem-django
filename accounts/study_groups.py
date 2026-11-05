"""Öquv guruhlari qoidalari (öqituvçi va admin panellari uçun umumiy).

- Öqituvçi guruh oça oladi (davr, dars vaqti va kunlari majburiy), lekin tahrirlay va öçira olmaydi.
- Öqituvçi faqat guruhsiz öquvçilarni guruhga qöşadi; öquvçining guruhini almaştiriş — admin işi.
- Kursga yoziliş sörovi faqat guruh tanlab tasdiqlanadi: guruhsiz öquvçi kursga qöşilmaydi.
- Guruh boşlaniş sanasidan tugaş sanasigaça faol (davomatda körinadi), keyin — arxiv.
"""
from .models import CustomUser, StudyGroup


def is_group_admin(user):
    return bool(user.is_admin_or_assistant)


def assignable_groups(user, profession):
    """Öquvçini qöşiş mumkin bölgan guruhlar: arxiv bölmagan; öqituvçiga — faqat öz guruhlari."""
    qs = StudyGroup.objects.not_archived().filter(profession=profession)
    if user.role == 'teacher':
        qs = qs.filter(teacher=user)
    return qs.select_related('teacher').order_by('start_date', 'start_time', 'name')


def grouped_student_ids(profession):
    """Şu kursning arxiv bölmagan biror guruhida turgan öquvçilar."""
    return set(
        StudyGroup.objects.not_archived().filter(profession=profession).exclude(students=None)
        .values_list('students', flat=True)
    )


def ungrouped_students(profession, students=None):
    """Kursga yozilgan, lekin hali hech bir (arxiv bölmagan) guruhga qöşilmagan öquvçilar."""
    qs = students if students is not None else CustomUser.objects.filter(role='student', is_blocked=False)
    return (qs.filter(enrollments__profession=profession)
            .exclude(pk__in=grouped_student_ids(profession))
            .distinct().order_by('first_name', 'last_name'))


def attach_group_options(requests, user):
    """Har bir yoziliş söroviga `group_options` (tanlaş mumkin bölgan guruhlar) qöşadi."""
    cache = {}
    for req in requests:
        key = req.profession_id
        if key not in cache:
            cache[key] = list(assignable_groups(user, req.profession))
        req.group_options = cache[key]
    return requests


def resolve_group(user, profession, group_id):
    """Formadan kelgan guruh id'si: ruxsat etilgan guruh yoki None."""
    try:
        group_id = int(group_id)
    except (TypeError, ValueError):
        return None
    return assignable_groups(user, profession).filter(pk=group_id).first()
