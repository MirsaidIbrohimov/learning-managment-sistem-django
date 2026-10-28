"""Ustoz daromadini kasb (Profession) stavkalari böyiça hisoblaş.

Har kasbning öz stavkasi bor: ``Profession.price_per_video`` /
``price_per_test`` / ``price_per_homework``. Ustoz bir neçta kasbga
biriktirilgan bölsa, daromad har kasb böyiça alohida hisoblanib jamlanadi.

Bu modul teacher va admin panellaridagi daromad hisob-kitobini bitta joyda
saqlaydi — kod takrorlanişining oldini oladi (DRY).

Eslatma: video içidagi "video-quiz" mukofoti (5+ savol uçun bir martalik)
alohida mexanizm (``video_quiz`` app) va bu yerda hisoblanmaydi.
"""
from django.db.models import Count

from .models import Lesson

# Ustozga tölanadigan dars turlari (qolganlari bepul: dictionary, speaking).
PAID_LESSON_TYPES = ('video', 'test', 'homework')


def _rate_map(professions, lesson_type):
    """{profession_id: stavka} — berilgan dars turi uçun."""
    return {p.id: p.teacher_rate(lesson_type) for p in professions}


def _aggregate(prof_count_rows, rate_by_prof):
    """Sof (DB'siz) yordamçi — test qilinadi.

    prof_count_rows : ``[(profession_id, count), ...]``
    rate_by_prof    : ``{profession_id: rate}``
    return          : ``(jami_soni, jami_summa)``
    """
    total_count = 0
    total_amount = 0
    for prof_id, count in prof_count_rows:
        total_count += count
        total_amount += count * rate_by_prof.get(prof_id, 0)
    return total_count, total_amount


def _filter_lessons(professions, lesson_type, created_by=None, start=None, end=None):
    qs = Lesson.objects.filter(profession__in=professions, lesson_type=lesson_type)
    if created_by is not None:
        qs = qs.filter(created_by=created_by)
    if start is not None:
        qs = qs.filter(created_at__gte=start)
    if end is not None:
        qs = qs.filter(created_at__lt=end)
    return qs


def type_earnings(professions, lesson_type, *, created_by=None, start=None, end=None):
    """Bitta dars turi uçun ``(count, total)`` — kasb stavkalariga qarab.

    professions : Profession röyxati/queryset (ustoz biriktirilgan kasblar)
    created_by  : faqat şu foydalanuvçi yaratgan darslar (ixtiyoriy)
    start, end  : ``created_at`` oraliği ``[start, end)`` (ixtiyoriy)
    """
    professions = list(professions)
    if not professions:
        return 0, 0
    rows = _filter_lessons(professions, lesson_type, created_by, start, end) \
        .values('profession').annotate(c=Count('id'))
    prof_count_rows = [(r['profession'], r['c']) for r in rows]
    return _aggregate(prof_count_rows, _rate_map(professions, lesson_type))


def lesson_items(professions, lesson_type, *, created_by=None, start=None, end=None):
    """Batafsil röyxat — har element öz stavkasi (``rate``) bilan.

    Har element: ``{id, title, profession__name, created_at, rate}``.
    """
    professions = list(professions)
    if not professions:
        return []
    rate_by_prof = _rate_map(professions, lesson_type)
    qs = _filter_lessons(professions, lesson_type, created_by, start, end)
    items = list(qs.values('id', 'title', 'profession', 'profession__name', 'created_at'))
    for it in items:
        it['rate'] = rate_by_prof.get(it.pop('profession'), 0)
    return items


def period_summary(professions, *, created_by=None, start=None, end=None, with_items=False):
    """video/test/homework böyiça ``{count, total[, items]}`` luğati.

    ``with_items=True`` bölsa, har tur uçun röyxat ham qaytadi va count/total
    öşa röyxatdan hisoblanadi (qöşimça aggregate sörovsiz).
    """
    professions = list(professions)
    data = {}
    for lt in PAID_LESSON_TYPES:
        if with_items:
            items = lesson_items(professions, lt, created_by=created_by, start=start, end=end)
            data[lt] = {
                'count': len(items),
                'total': sum(i['rate'] for i in items),
                'items': items,
            }
        else:
            count, total = type_earnings(
                professions, lt, created_by=created_by, start=start, end=end)
            data[lt] = {'count': count, 'total': total}
    return data


def profession_rate_rows(professions):
    """Şablon uçun stavkalar jadvali: ``[{name, video, test, homework}, ...]``."""
    return [{
        'name': p.name,
        'video': p.price_per_video,
        'test': p.price_per_test,
        'homework': p.price_per_homework,
    } for p in professions]


def uniform_rate(professions, lesson_type):
    """Barça kasblarda stavka bir xil bölsa — öşa qiymat; aks holda ``None``.

    Şablonda "Har biri X söm" yozuvini körsatish/berkitish uçun işlatiladi.
    """
    vals = {p.teacher_rate(lesson_type) for p in professions}
    return vals.pop() if len(vals) == 1 else None
