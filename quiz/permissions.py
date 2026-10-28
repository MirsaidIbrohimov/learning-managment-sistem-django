"""
Centralized permission logic for the quiz API — replaces the repeated
`if not (request.user.is_admin or request.user.is_teacher)` checks that were
scattered across accounts/views.py and teacher/views.py.

Roles (see accounts.models.CustomUser):
  - admin / assistant_admin: full access to every question and quiz.
  - teacher: access to questions/quizzes they created, plus quizzes attached
    to lessons under a profession they teach (`teaching_professions`).
  - student: no access to the authoring API. Phase 5 adds `IsStudent` below,
    scoped to the attempt-taking endpoints only.
"""
from rest_framework import permissions


class IsAdminOrTeacher(permissions.BasePermission):
    """Gate at the view level: only admins/assistant-admins/teachers may use
    the quiz authoring API at all. Object-level ownership is checked
    separately via can_access_question / can_access_quiz."""

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        return bool(user.is_admin or user.is_assistant_admin or user.is_teacher)


class IsStudent(permissions.BasePermission):
    """Gate for the Phase 5 attempt-taking API (AttemptViewSet). Admins and
    teachers manage/review attempts through the Django admin (see
    quiz.admin.AttemptAdmin) instead — this endpoint is exam-taking only."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user.is_authenticated and user.is_learner)


def can_take_quiz(student, quiz):
    """Whether `student` may start/resume an attempt on this quiz. Mirrors the
    enrollment check the legacy `student_start_test` view enforces (and the
    identical rule in accounts.views._can_view_course_stats): the student
    must be enrolled in the quiz's profession. A quiz not yet attached to a
    lesson (Phase 3+ standalone/bank-driven quizzes) has no profession to
    check against, so it's open to any authenticated student."""
    if not quiz.lesson_id or not quiz.lesson.profession_id:
        return True
    from accounts.models import CourseEnrollment  # local import: quiz must stay importable without accounts being app-ready yet

    profession = quiz.lesson.profession
    return (
        CourseEnrollment.objects.filter(user=student, profession=profession).exists()
        or student.profession_id == profession.id
    )


def quiz_prerequisites_met(student, quiz):
    """Yakuniy quiz uçun kursdagi barça oldingi darslar bajarilganmi."""
    if not quiz.lesson_id or not quiz.lesson.profession_id:
        return True

    from accounts.models import Test, final_test_prerequisites_met

    is_final = Test.objects.filter(lesson_id=quiz.lesson_id, test_type='final').exists()
    if not is_final:
        return True
    return final_test_prerequisites_met(student, quiz.lesson.profession)


def can_access_question(user, question):
    """Whether `user` (a teacher) may read/edit this bank question."""
    if user.is_admin or user.is_assistant_admin:
        return True
    if not user.is_teacher:
        return False
    if question.created_by_id == user.id:
        return True
    taught = user.teaching_professions.all()
    return question.quiz_links.filter(quiz__lesson__profession__in=taught).exists() or \
        question.quiz_links.filter(quiz__created_by=user).exists()


def can_access_quiz(user, quiz):
    """Whether `user` (a teacher) may read/edit this quiz."""
    if user.is_admin or user.is_assistant_admin:
        return True
    if not user.is_teacher:
        return False
    if quiz.created_by_id == user.id:
        return True
    if quiz.lesson_id and quiz.lesson.profession_id:
        return user.teaching_professions.filter(pk=quiz.lesson.profession_id).exists()
    return False
