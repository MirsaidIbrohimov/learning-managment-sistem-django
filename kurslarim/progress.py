"""Portal uchun darslar ketma-ketligi — asosiy tizimdagi qoidalar bilan bir xil.

Bo'lim ochiladi, agar: birinchi bo'lim bo'lsa, boshlangan/tugatilgan bo'lsa yoki
oldingi bo'lim to'liq bajarilgan bo'lsa. Kunlik cheklov yoqilgan kursda bir
kunda faqat bitta yangi bo'limga kiriladi. Progress asosiy tizim modellarida
saqlanadi, shuning uchun hisob ochilgach o'quvchi shu joyidan davom etadi.
"""
from datetime import date

from accounts.models import (
    DailySectionAccess, HomeworkSubmission, SpeakingSubmission, TestResult, VideoProgress,
    daily_limit_active,
)


def portal_supports(lesson):
    """Portalda bajarib bo'ladigan dars turlari."""
    if lesson.lesson_type in ('video', 'homework', 'dictionary'):
        return True
    if lesson.lesson_type == 'test':
        from quiz.models import Quiz
        quiz = getattr(lesson, 'quiz', None)
        return bool(quiz and quiz.status == Quiz.Status.PUBLISHED)
    return False


def _is_required(lesson):
    # Lug'at hech qachon talab qilinmaydi; portalda ochilmaydigan darslar
    # (speaking, eski tizimdagi test) o'quvchini to'xtatib qo'ymasligi kerak.
    return lesson.lesson_type != 'dictionary' and portal_supports(lesson)


def completed_lesson_ids(user, profession):
    from quiz.models import Attempt

    watched = VideoProgress.objects.filter(
        user=user, watched=True, video__lesson__profession=profession,
    ).values_list('video__lesson_id', flat=True)
    passed_legacy = TestResult.objects.filter(
        student=user, test__lesson__profession=profession, passed=True,
    ).values_list('test__lesson_id', flat=True)
    passed_quiz = Attempt.objects.filter(
        student=user, quiz__lesson__profession=profession, passed=True,
        status__in=[Attempt.Status.SUBMITTED, Attempt.Status.GRADED],
    ).values_list('quiz__lesson_id', flat=True)
    accepted = HomeworkSubmission.objects.filter(
        student=user, homework__lesson__profession=profession, status__in=['accepted', 'graded'],
    ).values_list('homework__lesson_id', flat=True)
    speaking = SpeakingSubmission.objects.filter(
        student=user, speaking_task__lesson__profession=profession, status='graded',
    ).values_list('speaking_task__lesson_id', flat=True)
    return set(watched) | set(passed_legacy) | set(passed_quiz) | set(accepted) | set(speaking)


def course_state(user, profession):
    """Bo'limlar, darslar, qulflar va keyingi dars uchun tartiblangan ro'yxat."""
    done = completed_lesson_ids(user, profession)
    limit_on = daily_limit_active(user, profession)
    today_access = DailySectionAccess.objects.filter(
        user=user, profession=profession, accessed_date=date.today(),
    ).first()

    sections = list(profession.sections.filter(is_active=True).order_by('order', 'created_at')
                    .prefetch_related('lessons__quiz'))
    result, ordered, lesson_lock = [], [], {}
    prev_required = None
    for idx, section in enumerate(sections):
        lessons = list(section.lessons.all())
        required = {l.pk for l in lessons if _is_required(l)}
        completed = required.issubset(done)
        started = bool(required & done)
        if not required or completed or started or idx == 0:
            lock = False
        elif prev_required is not None and not prev_required.issubset(done):
            lock = 'sequential'
        elif limit_on and today_access and today_access.section_id != section.id:
            lock = 'daily'
        else:
            lock = False
        prev_required = required
        items = []
        for lesson in lessons:
            lesson_lock[lesson.pk] = False if lesson.lesson_type == 'dictionary' else lock
            items.append({'lesson': lesson, 'completed': lesson.pk in done,
                          'locked': lesson_lock[lesson.pk], 'supported': portal_supports(lesson)})
            ordered.append(lesson)
        result.append({'section': section, 'locked': lock, 'completed': bool(required) and completed,
                       'lessons': items, 'done': len(required & done), 'total': len(required),
                       'percent': int(100 * len(required & done) / len(required)) if required else 0})

    loose = list(profession.lessons.filter(section__isnull=True).prefetch_related('quiz'))
    loose_items = []
    for lesson in loose:
        lesson_lock[lesson.pk] = False
        loose_items.append({'lesson': lesson, 'completed': lesson.pk in done,
                            'locked': False, 'supported': portal_supports(lesson)})
        ordered.append(lesson)

    required_all = {l.pk for l in ordered if _is_required(l)}
    # "Davom ettirish" — birinchi ochiq va hali bajarilmagan dars.
    resume = next((l for l in ordered if _is_required(l) and l.pk not in done
                   and not lesson_lock.get(l.pk)), None)
    return {
        'resume': resume,
        'sections': result,
        'loose_lessons': loose_items,
        'ordered': ordered,
        'lesson_lock': lesson_lock,
        'done': done,
        'limit_on': limit_on,
        'today_access': today_access,
        'done_count': len(required_all & done),
        'total_count': len(required_all),
    }


def open_lesson(user, profession, lesson):
    """Darsga kirishni tekshiradi. Qaytaradi: (state, xato_xabari yoki None)."""
    state = course_state(user, profession)
    lock = state['lesson_lock'].get(lesson.pk, False)
    if lock == 'sequential':
        return state, "Avval oldingi bo'limdagi barcha darslarni bajaring! 🔒"
    if lock == 'daily':
        return state, (f"Bugun siz faqat \"{state['today_access'].section.title}\" bo'limini o'qiy olasiz. "
                       "Yangi bo'limga ertaga kirishingiz mumkin! 📚")
    if (lesson.section_id and lesson.pk not in state['done'] and state['limit_on']
            and lesson.lesson_type != 'dictionary' and not state['today_access']):
        section_done = next((s['completed'] for s in state['sections'] if s['section'].pk == lesson.section_id), False)
        if not section_done:
            DailySectionAccess.objects.get_or_create(
                user=user, profession=profession, accessed_date=date.today(),
                defaults={'section_id': lesson.section_id},
            )
    return state, None


def next_lesson_after(state, lesson):
    ordered = state['ordered']
    for idx, item in enumerate(ordered):
        if item.pk == lesson.pk:
            return ordered[idx + 1] if idx + 1 < len(ordered) else None
    return None
