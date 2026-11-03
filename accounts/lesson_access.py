"""Öquvçi darsga kira oladimi — sayt va ilova uçun yagona qoida.

Avval bu mantiq `student_lesson_view` içida edi. Ilova API'si ham xuddi şu
qoidaga amal qilişi kerak, aks holda sayt qulflagan darsni ilova oçib qöyardi.
"""
from datetime import date

from .models import (
    DailySectionAccess, HomeworkSubmission, Lesson, SpeakingSubmission, TestResult, VideoProgress,
    completed_course_lesson_ids, daily_limit_active, final_lesson_q,
)

FINAL = 'final'
SEQUENTIAL = 'sequential'
DAILY = 'daily'


class LessonGate:
    """Bitta kurs böyiça kiriş qoidasi. Bir marta yuklanadi, röyxatda N+1 sörov bölmaydi."""

    def __init__(self, user, profession):
        self.user = user
        self.profession = profession
        self.today = date.today()
        self.completed = completed_course_lesson_ids(user, profession)
        self.limit_on = daily_limit_active(user, profession)
        self.today_access = DailySectionAccess.objects.filter(
            user=user, profession=profession, accessed_date=self.today,
        ).select_related('section').first()
        self.section_order = list(
            profession.sections.filter(is_active=True).order_by('order', 'created_at').values_list('pk', flat=True)
        )
        self.section_lessons = {}
        self.required = set()
        for pk, section_id in Lesson.objects.filter(profession=profession).exclude(
            lesson_type='dictionary',
        ).values_list('pk', 'section_id'):
            self.section_lessons.setdefault(section_id, set()).add(pk)
        self.final_ids = set(
            Lesson.objects.filter(profession=profession, lesson_type='test').filter(final_lesson_q()).values_list('pk', flat=True)
        )
        self.required = set().union(*self.section_lessons.values()) - self.final_ids if self.section_lessons else set()

    @property
    def final_ready(self):
        return self.required.issubset(self.completed)

    def block(self, lesson):
        """Kiriş yöpiq bölsa (kod, xabar), oçiq bölsa None."""
        if lesson.pk in self.final_ids and not self.final_ready:
            return FINAL, "Yakuniy test oçilişi uçun avval kursdagi barça video, vazifa va testlarni bajaring!"
        if lesson.lesson_type == 'dictionary' or lesson.pk in self.completed or not lesson.section_id:
            return None

        own = self.section_lessons.get(lesson.section_id, set())
        if own & self.completed or own.issubset(self.completed):
            return None

        if lesson.section_id in self.section_order:
            idx = self.section_order.index(lesson.section_id)
            if idx > 0:
                previous = self.section_lessons.get(self.section_order[idx - 1], set())
                if not previous.issubset(self.completed):
                    return SEQUENTIAL, "Avval oldingi bölimdagi barça darslarni bajaring! 🔒"

        if self.limit_on and self.today_access and self.today_access.section_id != lesson.section_id:
            return DAILY, (
                f"Bugun siz faqat \"{self.today_access.section.title}\" bölimini öqiyolasiz. "
                "Yangi bölimga ertaga kirişingiz mumkin! 📚"
            )
        return None

    def record_visit(self, lesson):
        """Kunlik çeklovda bugungi bölimni belgilaydi. Faqat dars haqiqatan oçilganda çaqiriladi."""
        if (
            not self.limit_on or lesson.lesson_type == 'dictionary' or not lesson.section_id
            or lesson.pk in self.completed or self.today_access
        ):
            return
        if self.section_lessons.get(lesson.section_id, set()).issubset(self.completed):
            return
        self.today_access, _ = DailySectionAccess.objects.get_or_create(
            user=self.user, profession=self.profession, accessed_date=self.today,
            defaults={'section_id': lesson.section_id},
        )


def lesson_progress_map(user, profession):
    """Har bir dars uçun öquvçi natijasi: sayt kurs sahifasidagi bilan bir xil ustuvorlikda."""
    from quiz.models import Attempt

    progress = {}
    for lesson_id in VideoProgress.objects.filter(
        user=user, watched=True, video__lesson__profession=profession,
    ).values_list('video__lesson_id', flat=True):
        progress[lesson_id] = {'attempted': True}

    for lesson_id, score, passed in TestResult.objects.filter(
        student=user, test__lesson__profession=profession,
    ).order_by('-completed_at').values_list('test__lesson_id', 'score', 'passed'):
        progress.setdefault(lesson_id, {'attempted': True, 'score': score, 'passed': passed})

    for lesson_id, score, passed in Attempt.objects.filter(
        student=user, quiz__lesson__profession=profession,
        status__in=[Attempt.Status.SUBMITTED, Attempt.Status.GRADED],
    ).order_by('-started_at').values_list('quiz__lesson_id', 'score', 'passed'):
        if lesson_id:
            progress.setdefault(lesson_id, {'attempted': True, 'score': score, 'passed': passed})

    for lesson_id, status, grade in HomeworkSubmission.objects.filter(
        student=user, homework__lesson__profession=profession,
    ).values_list('homework__lesson_id', 'status', 'grade'):
        progress[lesson_id] = {'attempted': True, 'status': status, 'grade': grade}

    for lesson_id, status, grade in SpeakingSubmission.objects.filter(
        student=user, speaking_task__lesson__profession=profession,
    ).order_by('submitted_at').values_list('speaking_task__lesson_id', 'status', 'grade'):
        progress[lesson_id] = {'attempted': True, 'status': status, 'grade': grade}

    return progress
