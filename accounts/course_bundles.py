"""Birlashgan kurslar (masalan HTML + CSS + JS → "Front End").

Qoidalar:
  * Öquvçi birlaşmadagi bitta kursni 100% tugatsa — qolgan kurslarga sörovsiz
    (va tölovsiz — birlaşmani admin özi tuzgan) yoziladi.
  * Barça kurslarni 100% tugatsa — birlaşma nomi bilan sertifikat beriladi.

Kurs "tugatilgan" hisoblanadi, agar: şu kurs sertifikati bor, yakuniy testdan
ötgan yoki portal progressi (video, test, vazifa) 100% bölsa.
"""
import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import (
    Certificate, CourseBundle, CourseBundleItem, CourseEnrollment, CourseEnrollmentRequest,
    CourseUnenrollRequest, CustomUser, HomeworkSubmission, Message, SpeakingSubmission, TestResult,
    VideoProgress,
)

logger = logging.getLogger(__name__)


# ---------------- Progress ----------------

def course_percent(user, profession):
    from kurslarim.progress import course_state
    state = course_state(user, profession)
    if not state['total_count']:
        return 0
    return int(100 * state['done_count'] / state['total_count'])


def course_completed(user, profession, percent=None):
    if Certificate.objects.filter(student=user, profession=profession, bundle__isnull=True).exists():
        return True
    from .certificates import student_passed_final_test
    if student_passed_final_test(user, profession):
        return True
    return (course_percent(user, profession) if percent is None else percent) >= 100


def bundle_progress(user, bundle, enrolled_ids=None):
    """Kartada körsatiş uçun: har bir kurs holati va umumiy foiz."""
    if enrolled_ids is None:
        enrolled_ids = set(CourseEnrollment.objects.filter(user=user).values_list('profession_id', flat=True))
    items = []
    for profession in bundle.ordered_courses():
        enrolled = profession.pk in enrolled_ids
        percent = course_percent(user, profession) if enrolled else 0
        done = course_completed(user, profession, percent) if enrolled else bool(
            Certificate.objects.filter(student=user, profession=profession, bundle__isnull=True).exists())
        items.append({'profession': profession, 'enrolled': enrolled, 'percent': 100 if done else percent,
                      'completed': done})
    total = len(items)
    return {
        'bundle': bundle,
        'items': items,
        'completed_count': sum(i['completed'] for i in items),
        'total': total,
        'percent': int(sum(i['percent'] for i in items) / total) if total else 0,
        'certificate': Certificate.objects.filter(student=user, bundle=bundle).first(),
    }


def bundle_cards(user, enrolled_ids):
    """Kurslar sahifasi uçun faol birlaşmalar. Öquvçida avval holat sinxronlanadi
    (signal ötkazib yuborgan holatlar uçun ham: masalan, admin qölda belgilagan progress)."""
    bundles = list(CourseBundle.objects.filter(is_active=True, items__isnull=False).distinct()
                   .prefetch_related('items__profession'))
    learner = user.is_authenticated and getattr(user, 'is_learner', False)
    cards = []
    for bundle in bundles:
        courses = bundle.ordered_courses()
        if learner and enrolled_ids & {p.pk for p in courses}:
            try:
                sync_user_bundle(user, bundle)
            except Exception:
                logger.exception('Birlashgan kursni tekşirişda xato (user=%s, bundle=%s)', user.pk, bundle.pk)
            enrolled_ids = set(CourseEnrollment.objects.filter(user=user).values_list('profession_id', flat=True))
            cards.append(bundle_progress(user, bundle, enrolled_ids))
        else:
            cards.append({'bundle': bundle, 'items': [{'profession': p, 'enrolled': False, 'percent': 0,
                                                       'completed': False} for p in courses],
                          'completed_count': 0, 'total': len(courses), 'percent': None, 'certificate': None})
    return cards


def bundles_for_course(user, profession):
    """Kurs sahifasi uçun: şu kurs kiradigan faol birlaşmalar progressi."""
    if not user.is_authenticated or not getattr(user, 'is_learner', False):
        return []
    bundles = (CourseBundle.objects.filter(is_active=True, items__profession=profession).distinct()
               .prefetch_related('items__profession'))
    enrolled_ids = set(CourseEnrollment.objects.filter(user=user).values_list('profession_id', flat=True))
    return [bundle_progress(user, b, enrolled_ids) for b in bundles]


# ---------------- Avtomatik yoziliş va sertifikat ----------------

def _notify(student, title, content):
    try:
        Message.objects.create(title=title, content=content, message_type='achievement', recipient=student)
        if student.telegram_id:
            from telegram_bot.utils import notify_user
            notify_user(student.telegram_id, f"<b>{title}</b>\n\n{content}")
    except Exception:
        logger.exception('Birlashgan kurs xabari yuborilmadi (user=%s)', student.pk)


def enroll_remaining(user, bundle):
    """Birlaşmadagi hali yozilmagan kurslarga sörovsiz yoziş. Yangi yozilgan kurslarni qaytaradi."""
    from .course_membership import notify_student_joined
    added = []
    for profession in bundle.ordered_courses():
        if profession.is_blocked:
            continue
        _, created = CourseEnrollment.objects.get_or_create(user=user, profession=profession)
        if not created:
            continue
        CourseEnrollmentRequest.objects.filter(user=user, profession=profession).delete()
        CourseUnenrollRequest.objects.filter(user=user, profession=profession).delete()
        notify_student_joined(user, profession, how=f"\"{bundle.name}\" birlashgan kursi — avtomatik yozildi")
        added.append(profession)
    if added:
        names = ', '.join(f'"{p.name}"' for p in added)
        _notify(user, f"📚 {bundle.name}: yangi kurslar oçildi",
                f"Siz \"{bundle.name}\" yönalişidagi kursni tugatdingiz va {names} kurslariga "
                f"avtomatik yozildingiz. Hammasini 100% tugatsangiz — \"{bundle.name}\" sertifikati beriladi.")
    return added


def issue_bundle_certificate(user, bundle):
    """Barça kurslar tugatilgan bölsa sertifikat beradi. (cert | None, xato | None)."""
    existing = Certificate.objects.filter(student=user, bundle=bundle).first()
    if existing:
        return existing, None
    if not bundle.series_code.strip():
        return None, f"\"{bundle.name}\" uçun sertifikat seriya kodi sozlanmagan."
    courses = bundle.ordered_courses()
    if not courses or not all(course_completed(user, p) for p in courses):
        return None, "Hali barça kurslar tugatilmagan."
    today = timezone.localdate()
    try:
        valid_until = today.replace(year=today.year + bundle.validity_years)
    except ValueError:  # 29-fevral
        valid_until = today.replace(year=today.year + bundle.validity_years, day=28)
    with transaction.atomic():
        CustomUser.objects.select_for_update().get(pk=user.pk)
        existing = Certificate.objects.filter(student=user, bundle=bundle).first()
        if existing:
            return existing, None
        cert = Certificate.objects.create(
            student=user, profession=courses[0], bundle=bundle,
            certificate_id=bundle.generate_certificate_id(), status='active',
            valid_from=today, valid_until=valid_until,
            description=f"\"{bundle.name}\" yönalişidagi barça kurslarni ({len(courses)} ta) "
                        f"100% tugatgani uçun avtomatik berildi.",
        )
    from .certificates import _notify_certificate_telegram, regenerate_certificate_file
    regenerate_certificate_file(cert)
    _notify(user, "🎓🎉 Tabriklaymiz! Sertifikat berildi!",
            f"Siz \"{bundle.name}\" yönalişidagi barça kurslarni tugatdingiz!\n\n"
            f"🏅 Seriya: {cert.certificate_id}\n"
            f"⏳ Amal qiliş muddati: {cert.valid_until.strftime('%d.%m.%Y')}\n\n"
            f"📜 Profilingizdagi \"Sertifikatlarim\" bölimidan yuklab olişingiz mumkin.")
    try:
        _notify_certificate_telegram(cert)
    except Exception:
        logger.exception('Birlashgan kurs sertifikati Telegram xabari xatosi (cert=%s)', cert.pk)
    return cert, None


def sync_user_bundle(user, bundle):
    """Bitta öquvçi va birlaşma uçun: tugatilgan kurs bölsa — qolganlariga yoziş, hammasi bölsa — sertifikat."""
    if not bundle.is_active or not getattr(user, 'is_learner', False):
        return
    courses = bundle.ordered_courses()
    if not courses:
        return
    enrolled = set(CourseEnrollment.objects.filter(user=user, profession__in=courses)
                   .values_list('profession_id', flat=True))
    done = [p for p in courses if (p.pk in enrolled or Certificate.objects.filter(
        student=user, profession=p, bundle__isnull=True).exists()) and course_completed(user, p)]
    if not done:
        return
    enroll_remaining(user, bundle)
    if len(done) == len(courses):
        cert, error = issue_bundle_certificate(user, bundle)
        if error and not cert:
            logger.info('Birlashgan kurs sertifikati berilmadi (user=%s, bundle=%s): %s', user.pk, bundle.pk, error)


def sync_user(user, profession_id=None):
    bundles = CourseBundle.objects.filter(is_active=True)
    if profession_id is not None:
        bundles = bundles.filter(items__profession_id=profession_id)
    for bundle in bundles.distinct():
        try:
            sync_user_bundle(user, bundle)
        except Exception:
            logger.exception('Birlashgan kursni tekşirişda xato (user=%s, bundle=%s)', user.pk, bundle.pk)


def sync_bundle(bundle):
    """Birlaşmadagi kurslarga yozilgan barça öquvçilarni tekşiriş (admin saqlaganda / buyruqda)."""
    user_ids = set(CourseEnrollment.objects.filter(
        profession__bundle_items__bundle=bundle, user__role__in=('student', 'assistant_admin'),
    ).values_list('user_id', flat=True))
    for user in CustomUser.objects.filter(pk__in=user_ids):
        try:
            sync_user_bundle(user, bundle)
        except Exception:
            logger.exception('Birlashgan kursni tekşirişda xato (user=%s, bundle=%s)', user.pk, bundle.pk)
    return len(user_ids)


# ---------------- Signal: dars bajarilganda tekşiriş ----------------

def _schedule(user_id, profession_id):
    if not user_id or not profession_id:
        return
    if not CourseBundleItem.objects.filter(profession_id=profession_id, bundle__is_active=True).exists():
        return

    def run():
        user = CustomUser.objects.filter(pk=user_id).first()
        if user:
            sync_user(user, profession_id)
    transaction.on_commit(run)


@receiver(post_save, sender=VideoProgress, dispatch_uid='bundle-video')
def _on_video(sender, instance, raw=False, **kwargs):
    if not raw and instance.watched:
        _schedule(instance.user_id, VideoProgress.objects.filter(pk=instance.pk)
                  .values_list('video__lesson__profession_id', flat=True).first())


@receiver(post_save, sender=TestResult, dispatch_uid='bundle-test')
def _on_test(sender, instance, raw=False, **kwargs):
    if not raw and instance.passed:
        _schedule(instance.student_id, TestResult.objects.filter(pk=instance.pk)
                  .values_list('test__lesson__profession_id', flat=True).first())


@receiver(post_save, sender=HomeworkSubmission, dispatch_uid='bundle-homework')
def _on_homework(sender, instance, raw=False, **kwargs):
    if not raw and instance.status in ('accepted', 'graded'):
        _schedule(instance.student_id, HomeworkSubmission.objects.filter(pk=instance.pk)
                  .values_list('homework__lesson__profession_id', flat=True).first())


@receiver(post_save, sender=SpeakingSubmission, dispatch_uid='bundle-speaking')
def _on_speaking(sender, instance, raw=False, **kwargs):
    if not raw and instance.status == 'graded':
        _schedule(instance.student_id, SpeakingSubmission.objects.filter(pk=instance.pk)
                  .values_list('speaking_task__lesson__profession_id', flat=True).first())


@receiver(post_save, sender=Certificate, dispatch_uid='bundle-certificate')
def _on_certificate(sender, instance, raw=False, **kwargs):
    if not raw and not instance.bundle_id and instance.student_id:
        _schedule(instance.student_id, instance.profession_id)


def _connect_quiz():
    from quiz.models import Attempt

    @receiver(post_save, sender=Attempt, dispatch_uid='bundle-quiz')
    def _on_attempt(sender, instance, raw=False, **kwargs):
        if not raw and instance.passed:
            _schedule(instance.student_id, Attempt.objects.filter(pk=instance.pk)
                      .values_list('quiz__lesson__profession_id', flat=True).first())


_connect_quiz()
