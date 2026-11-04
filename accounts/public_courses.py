"""Sotuvdagi (bir martalik tölovli) kurslar uçun oçiq SEO sahifalari.

Login talab qilinmaydi — Google va boşqa qidiruv tizimlari kurs sahifasini
indekslab, foydalanuvçini töğridan-töğri xarid sahifasiga olib keladi.
Faqat marketing ma'lumoti körsatiladi: dars nomlari, narx, ustozlar.
Dars mazmuni (video, vazifa, test) yopiqligiça qoladi.
"""
import json

from django.conf import settings
from django.db.models import Count, Prefetch, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.html import strip_tags
from django.utils.text import Truncator

from .course_pricing import attach_prices
from .models import Lesson, Profession

FAQ = (
    ("Kursga qanday yoziladi?",
     "«Sotib oliş» tugmasini bosing, tizimga kiring yoki röyxatdan öting va onlayn tölovni amalga "
     "oşiring. Tölov tasdiqlangan zahoti kurs avtomatik oçiladi — sörov kutiş şart emas."),
    ("Tölov bir martalikmi?",
     "Ha. Kurs uçun bir marta tölaysiz va unga umrbod kiriş huquqini olasiz. Oylik tölov talab qilinmaydi."),
    ("Qanday tölaş mumkin?",
     "Click, Payme, Uzum Bank, Paynet hamda HUMO va Uzcard kartalari orqali onlayn. Hisobingizdagi "
     "balansdan ham tölaşingiz mumkin."),
    ("Kurs tugagaç sertifikat beriladimi?",
     "Sertifikat joriy qilingan kurslarda barça darslarni tugatgan öquvçiga sertifikat beriladi."),
)


def sale_courses():
    return Profession.objects.filter(
        is_paid=True, one_time_payment=True, one_time_price__gt=0, is_blocked=False, is_mandatory=False,
    )


def _origin():
    return getattr(settings, 'SEO_CANONICAL_ORIGIN', 'https://itc-academy.uz').rstrip('/')


def _summary(profession, limit=160):
    text = ' '.join(strip_tags(profession.description or '').split())
    return Truncator(text).chars(limit) if text else f"{profession.name} — IT Creative Academy onlayn kursi."


def _ld(data):
    # </script> ni yopib qöymasligi uçun.
    return json.dumps(data, ensure_ascii=False).replace('</', '<\\/')


def _organization(origin):
    return {'@type': 'Organization', 'name': 'IT Creative Academy', 'url': origin + '/',
            'logo': origin + '/static/images/logo.png'}


def catalog(request):
    origin = _origin()
    courses = list(sale_courses().annotate(
        lesson_total=Count('lessons', distinct=True),
        student_total=Count('enrollments', filter=Q(enrollments__user__role='student'), distinct=True),
    ).order_by('-created_at'))
    attach_prices(courses)
    ld = {
        '@context': 'https://schema.org', '@type': 'ItemList', 'name': 'IT Creative Academy onlayn kurslari',
        'itemListElement': [
            {'@type': 'ListItem', 'position': i, 'url': origin + c.public_url, 'name': c.name}
            for i, c in enumerate(courses, 1)
        ],
    }
    return render(request, 'accounts/public/course_catalog.html', {
        'courses': courses, 'seo_origin': origin, 'ld_json': _ld(ld),
    })


def course_landing(request, pk, slug=None):
    course = get_object_or_404(sale_courses().prefetch_related('teachers'), pk=pk)
    if slug != course.seo_slug:
        # Yagona kanonik URL — dublikat sahifalar indeksga tuşmasin.
        return redirect(course.public_url, permanent=True)

    origin = _origin()
    lessons_qs = Lesson.objects.order_by('order', 'created_at').only('pk', 'title', 'lesson_type', 'section_id')
    sections = list(course.sections.filter(is_active=True).order_by('order', 'created_at')
                    .prefetch_related(Prefetch('lessons', queryset=lessons_qs)))
    lesson_counts = {row['lesson_type']: row['n'] for row in
                     course.lessons.values('lesson_type').annotate(n=Count('id'))}
    total_lessons = sum(lesson_counts.values())

    purchased = False
    if request.user.is_authenticated and getattr(request.user, 'is_learner', False):
        from kurslarim.access import purchased_course_ids
        purchased = course.pk in purchased_course_ids(request.user)

    summary = _summary(course)
    url = origin + course.public_url
    image = origin + course.photo.url if course.photo else origin + '/static/images/logo.png'
    ld = [
        {
            '@context': 'https://schema.org', '@type': 'Course',
            'name': course.name, 'description': _summary(course, 500), 'url': url, 'image': image,
            'inLanguage': 'uz', 'provider': _organization(origin),
            'offers': {
                '@type': 'Offer', 'category': 'Paid', 'price': str(course.sale.price),
                'priceCurrency': 'UZS', 'availability': 'https://schema.org/InStock', 'url': url,
                **({'priceValidUntil': course.sale.ends_at.date().isoformat()} if course.sale.ends_at else {}),
            },
            'hasCourseInstance': {
                '@type': 'CourseInstance', 'courseMode': 'Online',
                **({'courseWorkload': f'P{course.duration_months}M'} if course.duration_months else {}),
            },
        },
        {
            '@context': 'https://schema.org', '@type': 'BreadcrumbList',
            'itemListElement': [
                {'@type': 'ListItem', 'position': 1, 'name': 'Boş sahifa', 'item': origin + '/'},
                {'@type': 'ListItem', 'position': 2, 'name': 'Kurslar', 'item': origin + '/kurslar/'},
                {'@type': 'ListItem', 'position': 3, 'name': course.name, 'item': url},
            ],
        },
        {
            '@context': 'https://schema.org', '@type': 'FAQPage',
            'mainEntity': [{'@type': 'Question', 'name': q,
                            'acceptedAnswer': {'@type': 'Answer', 'text': a}} for q, a in FAQ],
        },
    ]
    return render(request, 'accounts/public/course_landing.html', {
        'course': course, 'sections': sections, 'total_lessons': total_lessons,
        'video_count': lesson_counts.get('video', 0), 'test_count': lesson_counts.get('test', 0),
        'homework_count': lesson_counts.get('homework', 0),
        'student_count': course.student_count(), 'teachers': list(course.teachers.all()),
        'faq': FAQ, 'purchased': purchased, 'summary': summary,
        'seo_origin': origin, 'seo_image': image, 'ld_json': _ld(ld),
    })


def course_short(request, pk):
    """/kurslar/<id>/ → kanonik slugli manzil."""
    course = sale_courses().filter(pk=pk).first()
    if course is None:
        raise Http404
    return redirect(course.public_url, permanent=True)
