"""Final exam summaries and free, single-use retries granted by admins."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import CourseEnrollment, CustomUser
from quiz.models import Attempt, Quiz, QuizRetryPayment


def final_quizzes(profession):
    return Quiz.objects.filter(lesson__profession=profession).filter(
        Q(lesson__test__test_type='final') | Q(settings__retry_payment_required=True)
    ).select_related('settings').distinct()


def final_exam_summary(student, profession):
    exams = []
    for quiz in final_quizzes(profession):
        attempts = Attempt.objects.filter(student=student, quiz=quiz)
        result = attempts.filter(status__in=[Attempt.Status.SUBMITTED, Attempt.Status.GRADED]).order_by('-started_at', '-pk').first()
        active = attempts.filter(status=Attempt.Status.IN_PROGRESS).exists()
        approved = QuizRetryPayment.objects.filter(student=student, quiz=quiz, status='approved').exists()
        settings_ = getattr(quiz, 'settings', None)
        exams.append({
            'quiz': quiz, 'result': result, 'active': active,
            'participated': attempts.exists(), 'retry_available': approved,
            'can_grant': bool(result and not result.passed and not active and not approved
                              and quiz.status == Quiz.Status.PUBLISHED
                              and settings_ and settings_.retry_payment_required),
        })
    return exams


@login_required
@require_POST
@transaction.atomic
def admin_grant_exam_retry(request, user_pk, profession_pk, quiz_pk):
    if not request.user.is_admin:
        return redirect('home')
    # The checkout flow locks the same student, preventing duplicate grants.
    student = get_object_or_404(CustomUser.objects.select_for_update(), pk=user_pk, role='student')
    enrollment = get_object_or_404(CourseEnrollment, user=student, profession_id=profession_pk)
    quiz = get_object_or_404(final_quizzes(enrollment.profession), pk=quiz_pk, status=Quiz.Status.PUBLISHED)
    settings_ = getattr(quiz, 'settings', None)
    attempts = Attempt.objects.filter(student=student, quiz=quiz)
    result = attempts.filter(status__in=[Attempt.Status.SUBMITTED, Attempt.Status.GRADED]).order_by('-started_at', '-pk').first()
    if not settings_ or not settings_.retry_payment_required or not result or result.passed:
        messages.error(request, "Bu imtihon uchun qo'shimcha imkon berib bo'lmaydi.")
    elif attempts.filter(status=Attempt.Status.IN_PROGRESS).exists():
        messages.info(request, "O'quvchining davom etayotgan urinishi mavjud.")
    elif QuizRetryPayment.objects.filter(student=student, quiz=quiz, status='approved').exists():
        messages.info(request, "O'quvchiga qayta urinish imkoniyati allaqachon berilgan.")
    else:
        # The existing exam entry flow consumes one approved grant per retry.
        # Zero amount distinguishes this permission from a received payment.
        QuizRetryPayment.objects.create(
            student=student, quiz=quiz, amount=0, status='approved',
            reviewed_by=request.user, reviewed_at=timezone.now(),
        )
        messages.success(request, "Yakuniy imtihonga bitta bepul qayta urinish berildi.")
    from django.urls import reverse
    return redirect(reverse('admin_user_view', args=[student.pk]) + '#tab-daily-limit')
