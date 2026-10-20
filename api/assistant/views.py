"""Assistant Admin API views with granular permissions and audit log.

Har bir view o'zining `required_perm` orqali permission talab qiladi.
Admin (role='admin') yoki super_admin assistant_role barcha amallarni
bajara oladi. Boshqa rollar uchun faqat berilgan permissionlarga ruxsat.
"""

import logging

from django.contrib.auth.hashers import make_password
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import generics, status, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import (
    CustomUser, Homework, HomeworkSubmission,
    TestResult, Certificate,
    Message, HelpRequest, CourseApplication,
    PasswordResetRequest, Parent, ParentMessage, ParentPasswordResetRequest,
    CourseEnrollmentRequest, CourseUnenrollRequest, PremiumRequest,
    Book, BookRental, SurveyForm, SurveyQuestion, SurveyResponse,
    Lesson, AssistantRole, AssistantActionLog,
)
from blog.models import Post, PostComment
from teacher.models import TeacherAttendance

from api.permissions import HasAssistantPerm, IsAdminOrAssistant, IsNotBlocked
from accounts.permissions_registry import PERMISSIONS, all_permission_codes

from .audit import log_action
from .serializers import (
    AssistantUserSerializer,
    HomeworkSerializer, HomeworkSubmissionSerializer,
    TestResultDetailSerializer, LessonAnalyticsSerializer,
    TeacherAttendanceSerializer, CertificateSerializer,
    PasswordResetRequestSerializer, ParentSerializer, ParentMessageSerializer,
    ParentPasswordResetRequestSerializer,
    CourseEnrollmentRequestSerializer, CourseUnenrollRequestSerializer,
    PremiumRequestSerializer,
    MessageSerializer, BlogPostSerializer, BlogCommentSerializer,
    BookSerializer, BookRentalSerializer,
    HelpRequestSerializer, CourseApplicationSerializer,
    SurveyFormSerializer, SurveyQuestionSerializer, SurveyResponseSerializer,
)
from .serializers_roles import (
    AssistantRoleSerializer, AssistantActionLogSerializer,
)

audit = logging.getLogger('api.audit')

BASE_AUTH = [IsAuthenticated, IsNotBlocked]


def _perm(code):
    """Shortcut: permission_classes uchun [..., HasAssistantPerm.require(code)]"""
    return BASE_AUTH + [HasAssistantPerm.require(code)]


# ============================================================
# META: PERMISSIONS / ROLES / LOGS
# ============================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsNotBlocked, IsAdminOrAssistant])
def permission_registry(request):
    """Mavjud barcha permissionlar guruhlangan ko'rinishda."""
    out = {}
    for key, group in PERMISSIONS.items():
        out[key] = {
            'label': group['label'],
            'perms': [{'code': c, 'label': l} for c, l in group['perms'].items()],
        }
    return Response({
        'groups': out,
        'all_codes': all_permission_codes(),
        'my_permissions': sorted(request.user.get_assistant_permissions()),
        'is_super_admin': request.user.is_super_admin,
    })


class AssistantRoleListCreateView(generics.ListCreateAPIView):
    serializer_class = AssistantRoleSerializer
    permission_classes = _perm('system.roles_manage')
    queryset = AssistantRole.objects.all()

    def perform_create(self, serializer):
        role = serializer.save()
        log_action(self.request, 'roles.create', target=role,
                   description=f"Rol yaratildi: {role.name} ({role.code})")


class AssistantRoleDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AssistantRoleSerializer
    permission_classes = _perm('system.roles_manage')
    queryset = AssistantRole.objects.all()

    def perform_update(self, serializer):
        role = serializer.save()
        log_action(self.request, 'roles.update', target=role,
                   description=f"Rol yangilandi: {role.name}")

    def perform_destroy(self, instance):
        if instance.is_system:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Tizim rolini o'chirib bo'lmaydi")
        log_action(self.request, 'roles.delete', target=instance,
                   description=f"Rol o'chirildi: {instance.name}")
        instance.delete()


class ActionLogListView(generics.ListAPIView):
    serializer_class = AssistantActionLogSerializer
    permission_classes = _perm('system.logs_view')

    def get_queryset(self):
        qs = AssistantActionLog.objects.select_related('user').all()
        user_id = self.request.query_params.get('user')
        if user_id:
            qs = qs.filter(user_id=user_id)
        code = self.request.query_params.get('action_code')
        if code:
            qs = qs.filter(action_code__icontains=code)
        date_from = self.request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        date_to = self.request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        return qs


# ============================================================
# DASHBOARD
# ============================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsNotBlocked, IsAdminOrAssistant])
def assistant_dashboard(request):
    data = {
        'users': {
            'total': CustomUser.objects.count(),
            'students': CustomUser.objects.filter(role='student').count(),
            'teachers': CustomUser.objects.filter(role='teacher').count(),
            'blocked': CustomUser.objects.filter(is_blocked=True).count(),
        },
        'learning': {
            'homework_submissions_pending': HomeworkSubmission.objects.filter(status='pending').count(),
            'test_results_total': TestResult.objects.count(),
            'certificates_issued': Certificate.objects.count(),
        },
        'requests': {
            'password_reset_pending': PasswordResetRequest.objects.filter(status='pending').count(),
            'enrollment_pending': CourseEnrollmentRequest.objects.filter(status='pending').count(),
            'unenroll_pending': CourseUnenrollRequest.objects.filter(status='pending').count(),
            'premium_pending': PremiumRequest.objects.filter(status='pending').count(),
        },
        'support': {
            'help_pending': HelpRequest.objects.filter(status='pending').count(),
            'applications_new': CourseApplication.objects.filter(status='new', is_shaharcha=False).count(),
            'surveys_active': SurveyForm.objects.filter(is_active=True).count(),
        },
        'content': {
            'messages_total': Message.objects.count(),
            'blog_posts': Post.objects.count(),
            'books_total': Book.objects.count(),
            'rentals_active': BookRental.objects.filter(status='active').count(),
        },
        'server_time': timezone.now().isoformat(),
        'my_permissions': sorted(request.user.get_assistant_permissions()),
    }
    return Response(data)


# ============================================================
# 1) O'QUV JARAYONI
# ============================================================

# ---- Vazifalar ----

class HomeworkListView(generics.ListAPIView):
    serializer_class = HomeworkSerializer
    permission_classes = _perm('homework.view')
    queryset = Homework.objects.select_related('lesson__profession').all()
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['lesson__title', 'description']


class HomeworkSubmissionListView(generics.ListAPIView):
    serializer_class = HomeworkSubmissionSerializer
    permission_classes = _perm('homework.view')

    def get_queryset(self):
        qs = HomeworkSubmission.objects.select_related('student', 'homework__lesson').all()
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        homework_id = self.request.query_params.get('homework')
        if homework_id:
            qs = qs.filter(homework_id=homework_id)
        return qs.order_by('-submitted_at')


class HomeworkSubmissionUpdateView(generics.RetrieveUpdateDestroyAPIView):
    """Submission'ga baho/feedback berish, o'chirish (alohida permission)"""
    serializer_class = HomeworkSubmissionSerializer
    queryset = HomeworkSubmission.objects.all()

    def get_permissions(self):
        if self.request.method == 'DELETE':
            return [p() for p in _perm('homework.delete')]
        if self.request.method in ('PUT', 'PATCH'):
            return [p() for p in _perm('homework.review')]
        return [p() for p in _perm('homework.view')]

    def perform_update(self, serializer):
        sub = serializer.save(graded_by=self.request.user, graded_at=timezone.now())
        log_action(self.request, 'homework.review', target=sub,
                   description=f"Vazifa baholandi: {sub.student.full_name}, ball={sub.grade}")

    def perform_destroy(self, instance):
        log_action(self.request, 'homework.delete', target=instance,
                   description=f"Vazifa topshirig'i o'chirildi: #{instance.id}")
        instance.delete()


# ---- Test natijalari ----

class TestResultListView(generics.ListAPIView):
    serializer_class = TestResultDetailSerializer
    permission_classes = _perm('tests.view')

    def get_queryset(self):
        qs = TestResult.objects.select_related('student', 'test__lesson__profession').all()
        student_id = self.request.query_params.get('student')
        if student_id:
            qs = qs.filter(student_id=student_id)
        passed = self.request.query_params.get('passed')
        if passed in ('true', '1'):
            qs = qs.filter(passed=True)
        elif passed in ('false', '0'):
            qs = qs.filter(passed=False)
        return qs.order_by('-completed_at')


class TestResultDetailView(generics.RetrieveDestroyAPIView):
    serializer_class = TestResultDetailSerializer
    queryset = TestResult.objects.select_related('student', 'test__lesson').all()

    def get_permissions(self):
        if self.request.method == 'DELETE':
            return [p() for p in _perm('tests.delete')]
        return [p() for p in _perm('tests.view')]

    def perform_destroy(self, instance):
        log_action(self.request, 'tests.delete', target=instance,
                   description=f"Test natijasi o'chirildi: #{instance.id}")
        instance.delete()


# ---- Darslar tahlili ----

class LessonAnalyticsListView(generics.ListAPIView):
    serializer_class = LessonAnalyticsSerializer
    permission_classes = _perm('lessons_analytics.view')

    def get_queryset(self):
        qs = Lesson.objects.select_related('profession', 'section').all()
        profession_id = self.request.query_params.get('profession')
        if profession_id:
            qs = qs.filter(profession_id=profession_id)
        return qs.order_by('profession_id', 'order')


# ---- Davomat ----

class AttendanceListCreateView(generics.ListCreateAPIView):
    serializer_class = TeacherAttendanceSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [p() for p in _perm('attendance.add')]
        return [p() for p in _perm('attendance.view')]

    def get_queryset(self):
        qs = TeacherAttendance.objects.select_related('teacher').all()
        teacher_id = self.request.query_params.get('teacher')
        if teacher_id:
            qs = qs.filter(teacher_id=teacher_id)
        date_from = self.request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(date__gte=date_from)
        date_to = self.request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(date__lte=date_to)
        return qs

    def perform_create(self, serializer):
        att = serializer.save(created_by=self.request.user)
        log_action(self.request, 'attendance.add', target=att,
                   description=f"Davomat qo'shildi: {att.teacher.full_name} - {att.date} ({att.status})")


class AttendanceDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TeacherAttendanceSerializer
    queryset = TeacherAttendance.objects.all()

    def get_permissions(self):
        m = self.request.method
        if m == 'DELETE':
            return [p() for p in _perm('attendance.delete')]
        if m in ('PUT', 'PATCH'):
            return [p() for p in _perm('attendance.edit')]
        return [p() for p in _perm('attendance.view')]

    def perform_update(self, serializer):
        att = serializer.save()
        log_action(self.request, 'attendance.edit', target=att,
                   description=f"Davomat tahrirlandi: #{att.id}")

    def perform_destroy(self, instance):
        log_action(self.request, 'attendance.delete', target=instance,
                   description=f"Davomat o'chirildi: #{instance.id}")
        instance.delete()


# ---- Sertifikatlar (so'rovlar tizimi olib tashlangan — avtomatik beriladi) ----

class CertificateListView(generics.ListAPIView):
    serializer_class = CertificateSerializer
    permission_classes = _perm('certificate_requests.view')

    def get_queryset(self):
        qs = Certificate.objects.select_related('student', 'profession').all()
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        return qs


# ============================================================
# 2) FOYDALANUVCHILAR
# ============================================================

class UserListView(generics.ListAPIView):
    serializer_class = AssistantUserSerializer
    permission_classes = _perm('users.view')
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['first_name', 'last_name', 'username', 'phone']
    ordering_fields = ['date_joined', 'last_activity', 'first_name']

    def get_queryset(self):
        qs = CustomUser.objects.select_related('profession').all()
        role = self.request.query_params.get('role')
        if role:
            qs = qs.filter(role=role)
        is_blocked = self.request.query_params.get('is_blocked')
        if is_blocked in ('true', '1'):
            qs = qs.filter(is_blocked=True)
        elif is_blocked in ('false', '0'):
            qs = qs.filter(is_blocked=False)
        profession = self.request.query_params.get('profession')
        if profession:
            qs = qs.filter(profession_id=profession)
        return qs.order_by('-date_joined')


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AssistantUserSerializer
    queryset = CustomUser.objects.select_related('profession').all()

    def get_permissions(self):
        m = self.request.method
        if m == 'DELETE':
            return [p() for p in _perm('users.delete')]
        if m in ('PUT', 'PATCH'):
            return [p() for p in _perm('users.edit')]
        return [p() for p in _perm('users.view')]

    def perform_update(self, serializer):
        u = serializer.save()
        log_action(self.request, 'users.edit', target=u,
                   description=f"Foydalanuvchi tahrirlandi: {u.username}")

    def perform_destroy(self, instance):
        if instance.is_admin:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Adminni o'chirib bo'lmaydi")
        log_action(self.request, 'users.delete', target=instance,
                   description=f"Foydalanuvchi o'chirildi: {instance.username} ({instance.role})")
        instance.delete()


@api_view(['POST'])
@permission_classes(_perm('users.set_password'))
def user_set_password(request, pk):
    user = get_object_or_404(CustomUser, pk=pk)
    new_password = request.data.get('new_password', '').strip()
    if not new_password or len(new_password) < 6:
        return Response({'error': "Parol kamida 6 belgi bo'lishi kerak"}, status=400)
    user.set_password(new_password)
    user.save(update_fields=['password'])
    log_action(request, 'users.set_password', target=user,
               description=f"Parol qo'lda o'rnatildi: {user.username}")
    return Response({'status': 'ok'})


@api_view(['POST'])
@permission_classes(_perm('users.block'))
def user_toggle_block(request, pk):
    user = get_object_or_404(CustomUser, pk=pk)
    if user.is_admin:
        return Response({'error': "Admin foydalanuvchini bloklash mumkin emas"}, status=400)
    user.is_blocked = not user.is_blocked
    user.save(update_fields=['is_blocked'])
    log_action(request, 'users.block', target=user,
               description=f"{user.username} -> {'BLOK' if user.is_blocked else 'OCHIQ'}")
    return Response({'is_blocked': user.is_blocked})


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsNotBlocked, HasAssistantPerm.require('users.edit')])
def user_assign_role(request, pk):
    """Foydalanuvchiga assistant_role biriktirish.

    body: { 'role_code': 'support' | null }
    Faqat admin yoki system.roles_manage permission'iga ega bo'lganlar uchun.
    """
    if not (request.user.is_admin or request.user.has_assistant_perm('system.roles_manage')):
        return Response({'error': "Ruxsat yo'q"}, status=403)
    user = get_object_or_404(CustomUser, pk=pk)
    role_code = request.data.get('role_code')
    if role_code:
        try:
            role = AssistantRole.objects.get(code=role_code)
        except AssistantRole.DoesNotExist:
            return Response({'error': "Bunday rol topilmadi"}, status=404)
        user.assistant_role = role
    else:
        user.assistant_role = None
    user.save(update_fields=['assistant_role'])
    log_action(request, 'users.assign_role', target=user,
               description=f"Yordamchi rol o'zgartirildi: {user.username} -> {role_code or '(none)'}")
    return Response(AssistantUserSerializer(user).data)


# ---- Parol tiklash ----

class PasswordResetRequestListView(generics.ListAPIView):
    serializer_class = PasswordResetRequestSerializer
    permission_classes = _perm('password_resets.view')

    def get_queryset(self):
        qs = PasswordResetRequest.objects.select_related('user').all()
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        return qs


@api_view(['POST'])
@permission_classes(_perm('password_resets.review'))
def password_reset_review(request, pk):
    req = get_object_or_404(PasswordResetRequest, pk=pk)
    action = request.data.get('action')
    if action not in ('approve', 'reject'):
        return Response({'error': "action 'approve' yoki 'reject' bo'lishi kerak"}, status=400)
    req.status = 'approved' if action == 'approve' else 'rejected'
    req.admin_message = request.data.get('admin_message', '')
    req.reviewed_by = request.user
    req.save()
    if action == 'approve':
        user = req.user
        user.password = req.new_password
        user.save(update_fields=['password'])
    log_action(request, 'password_resets.review', target=req,
               description=f"Parol so'rovi {action}: {req.user.username}")
    return Response(PasswordResetRequestSerializer(req).data)


# ---- Ota-onalar ----

class ParentListCreateView(generics.ListCreateAPIView):
    serializer_class = ParentSerializer
    queryset = Parent.objects.all()
    filter_backends = [filters.SearchFilter]
    search_fields = ['first_name', 'last_name', 'phone', 'username']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [p() for p in _perm('parents.add')]
        return [p() for p in _perm('parents.view')]

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        raw_password = data.pop('password', None)
        if isinstance(raw_password, list):
            raw_password = raw_password[0]
        if not raw_password or len(str(raw_password)) < 6:
            return Response({'error': "Parol kamida 6 belgi bo'lishi kerak"}, status=400)
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        parent = serializer.save(password=make_password(str(raw_password)))
        children = request.data.getlist('children') if hasattr(request.data, 'getlist') else request.data.get('children', [])
        if children:
            parent.children.set(children)
        log_action(request, 'parents.add', target=parent,
                   description=f"Ota-ona qo'shildi: {parent.full_name}")
        return Response(self.get_serializer(parent).data, status=201)


class ParentDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ParentSerializer
    queryset = Parent.objects.all()

    def get_permissions(self):
        m = self.request.method
        if m == 'DELETE':
            return [p() for p in _perm('parents.delete')]
        if m in ('PUT', 'PATCH'):
            return [p() for p in _perm('parents.edit')]
        return [p() for p in _perm('parents.view')]

    def perform_update(self, serializer):
        p = serializer.save()
        log_action(self.request, 'parents.edit', target=p,
                   description=f"Ota-ona tahrirlandi: {p.full_name}")

    def perform_destroy(self, instance):
        log_action(self.request, 'parents.delete', target=instance,
                   description=f"Ota-ona o'chirildi: {instance.full_name}")
        instance.delete()


class ParentMessageListView(generics.ListAPIView):
    serializer_class = ParentMessageSerializer
    permission_classes = _perm('parents.view')

    def get_queryset(self):
        qs = ParentMessage.objects.select_related('parent', 'child').all()
        is_read = self.request.query_params.get('is_read')
        if is_read in ('true', '1'):
            qs = qs.filter(is_read=True)
        elif is_read in ('false', '0'):
            qs = qs.filter(is_read=False)
        return qs


@api_view(['POST'])
@permission_classes(_perm('parents.message_reply'))
def parent_message_reply(request, pk):
    msg = get_object_or_404(ParentMessage, pk=pk)
    reply = request.data.get('reply', '').strip()
    if not reply:
        return Response({'error': "Javob bo'sh bo'lmasligi kerak"}, status=400)
    msg.reply = reply
    msg.replied_by = request.user
    msg.replied_at = timezone.now()
    msg.is_read = True
    msg.save()
    log_action(request, 'parents.message_reply', target=msg,
               description=f"Ota-ona xabariga javob: {msg.parent.full_name}")
    return Response(ParentMessageSerializer(msg).data)


class ParentPasswordResetListView(generics.ListAPIView):
    serializer_class = ParentPasswordResetRequestSerializer
    permission_classes = _perm('parents.view')
    queryset = ParentPasswordResetRequest.objects.select_related('parent').all()


@api_view(['POST'])
@permission_classes(_perm('parents.password_review'))
def parent_password_reset_review(request, pk):
    req = get_object_or_404(ParentPasswordResetRequest, pk=pk)
    action = request.data.get('action')
    if action not in ('approve', 'reject'):
        return Response({'error': "action 'approve' yoki 'reject' bo'lishi kerak"}, status=400)
    req.status = 'approved' if action == 'approve' else 'rejected'
    req.reviewed_by = request.user
    req.reviewed_at = timezone.now()
    req.save()
    if action == 'approve':
        parent = req.parent
        parent.password = req.new_password
        parent.save(update_fields=['password'])
    log_action(request, 'parents.password_review', target=req,
               description=f"Ota-ona parol so'rovi {action}: {req.parent.full_name}")
    return Response(ParentPasswordResetRequestSerializer(req).data)


# ---- So'rovlar ----

class EnrollmentRequestListView(generics.ListAPIView):
    serializer_class = CourseEnrollmentRequestSerializer
    permission_classes = _perm('requests.enrollment_view')

    def get_queryset(self):
        qs = CourseEnrollmentRequest.objects.select_related('user', 'profession').all()
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        return qs


@api_view(['POST'])
@permission_classes(_perm('requests.enrollment_review'))
def enrollment_request_review(request, pk):
    req = get_object_or_404(CourseEnrollmentRequest, pk=pk)
    action = request.data.get('action')
    if action not in ('approve', 'reject'):
        return Response({'error': "action 'approve' yoki 'reject' bo'lishi kerak"}, status=400)
    req.status = 'approved' if action == 'approve' else 'rejected'
    if hasattr(req, 'reviewed_by'):
        req.reviewed_by = request.user
    if hasattr(req, 'reviewed_at'):
        req.reviewed_at = timezone.now()
    req.save()
    if action == 'approve':
        from accounts.models import CourseEnrollment
        CourseEnrollment.objects.get_or_create(user=req.user, profession=req.profession)
    log_action(request, 'requests.enrollment_review', target=req,
               description=f"Kursga yozilish so'rovi {action}: {req.user.username} -> {req.profession.name}")
    return Response(CourseEnrollmentRequestSerializer(req).data)


class UnenrollRequestListView(generics.ListAPIView):
    serializer_class = CourseUnenrollRequestSerializer
    permission_classes = _perm('requests.unenroll_view')

    def get_queryset(self):
        qs = CourseUnenrollRequest.objects.select_related('user', 'profession').all()
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        return qs


@api_view(['POST'])
@permission_classes(_perm('requests.unenroll_review'))
def unenroll_request_review(request, pk):
    req = get_object_or_404(CourseUnenrollRequest, pk=pk)
    action = request.data.get('action')
    if action not in ('approve', 'reject'):
        return Response({'error': "action 'approve' yoki 'reject' bo'lishi kerak"}, status=400)
    req.status = 'approved' if action == 'approve' else 'rejected'
    if hasattr(req, 'reviewed_by'):
        req.reviewed_by = request.user
    if hasattr(req, 'reviewed_at'):
        req.reviewed_at = timezone.now()
    req.save()
    if action == 'approve':
        from accounts.models import CourseEnrollment
        CourseEnrollment.objects.filter(user=req.user, profession=req.profession).delete()
    log_action(request, 'requests.unenroll_review', target=req,
               description=f"Kursdan chiqish so'rovi {action}: {req.user.username}")
    return Response(CourseUnenrollRequestSerializer(req).data)


class PremiumRequestListView(generics.ListAPIView):
    serializer_class = PremiumRequestSerializer
    permission_classes = _perm('requests.premium_view')

    def get_queryset(self):
        qs = PremiumRequest.objects.select_related('user').all()
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        return qs


@api_view(['POST'])
@permission_classes(_perm('requests.premium_review'))
def premium_request_review(request, pk):
    req = get_object_or_404(PremiumRequest, pk=pk)
    action = request.data.get('action')
    if action not in ('approve', 'reject'):
        return Response({'error': "action 'approve' yoki 'reject' bo'lishi kerak"}, status=400)
    req.status = 'approved' if action == 'approve' else 'rejected'
    if hasattr(req, 'reviewed_by'):
        req.reviewed_by = request.user
    if hasattr(req, 'reviewed_at'):
        req.reviewed_at = timezone.now()
    req.save()
    log_action(request, 'requests.premium_review', target=req,
               description=f"Premium so'rovi {action}: {req.user.username}")
    return Response(PremiumRequestSerializer(req).data)


# ============================================================
# 3) KONTENT
# ============================================================

class MessageListCreateView(generics.ListCreateAPIView):
    serializer_class = MessageSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [p() for p in _perm('messages.add')]
        return [p() for p in _perm('messages.view')]

    def get_queryset(self):
        qs = Message.objects.select_related('sender', 'recipient').all()
        message_type = self.request.query_params.get('type')
        if message_type:
            qs = qs.filter(message_type=message_type)
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        msg = serializer.save(sender=self.request.user)
        log_action(self.request, 'messages.add', target=msg,
                   description=f"Xabar yuborildi: {msg.title}")


class MessageDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MessageSerializer
    queryset = Message.objects.all()

    def get_permissions(self):
        if self.request.method == 'DELETE':
            return [p() for p in _perm('messages.delete')]
        if self.request.method in ('PUT', 'PATCH'):
            return [p() for p in _perm('messages.add')]
        return [p() for p in _perm('messages.view')]

    def perform_destroy(self, instance):
        log_action(self.request, 'messages.delete', target=instance,
                   description=f"Xabar o'chirildi: #{instance.id}")
        instance.delete()


# ---- Blog ----

class BlogPostListCreateView(generics.ListCreateAPIView):
    serializer_class = BlogPostSerializer
    queryset = Post.objects.select_related('author').all()

    def get_permissions(self):
        if self.request.method == 'POST':
            return [p() for p in _perm('blog.add')]
        return [p() for p in _perm('blog.view')]

    def perform_create(self, serializer):
        post = serializer.save(author=self.request.user)
        log_action(self.request, 'blog.add', target=post,
                   description=f"Blog post qo'shildi: {post.title}")


class BlogPostDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = BlogPostSerializer
    queryset = Post.objects.all()

    def get_permissions(self):
        m = self.request.method
        if m == 'DELETE':
            return [p() for p in _perm('blog.delete')]
        if m in ('PUT', 'PATCH'):
            return [p() for p in _perm('blog.edit')]
        return [p() for p in _perm('blog.view')]

    def perform_update(self, serializer):
        post = serializer.save()
        log_action(self.request, 'blog.edit', target=post,
                   description=f"Blog post tahrirlandi: {post.title}")

    def perform_destroy(self, instance):
        log_action(self.request, 'blog.delete', target=instance,
                   description=f"Blog post o'chirildi: {instance.title}")
        instance.delete()


class BlogCommentListView(generics.ListAPIView):
    serializer_class = BlogCommentSerializer
    permission_classes = _perm('blog.view')

    def get_queryset(self):
        qs = PostComment.objects.select_related('user', 'post').all()
        post_id = self.request.query_params.get('post')
        if post_id:
            qs = qs.filter(post_id=post_id)
        return qs


class BlogCommentDeleteView(generics.DestroyAPIView):
    permission_classes = _perm('blog.comment_delete')
    queryset = PostComment.objects.all()

    def perform_destroy(self, instance):
        log_action(self.request, 'blog.comment_delete', target=instance,
                   description=f"Blog izoh o'chirildi: #{instance.id}")
        instance.delete()


# ---- Kutubxona ----

class BookListCreateView(generics.ListCreateAPIView):
    serializer_class = BookSerializer
    queryset = Book.objects.all()
    filter_backends = [filters.SearchFilter]
    search_fields = ['title', 'author', 'isbn']

    def get_permissions(self):
        if self.request.method == 'POST':
            return [p() for p in _perm('library.book_add')]
        return [p() for p in _perm('library.view')]

    def perform_create(self, serializer):
        b = serializer.save()
        log_action(self.request, 'library.book_add', target=b,
                   description=f"Kitob qo'shildi: {b.title}")


class BookDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = BookSerializer
    queryset = Book.objects.all()

    def get_permissions(self):
        m = self.request.method
        if m == 'DELETE':
            return [p() for p in _perm('library.book_delete')]
        if m in ('PUT', 'PATCH'):
            return [p() for p in _perm('library.book_edit')]
        return [p() for p in _perm('library.view')]

    def perform_update(self, serializer):
        b = serializer.save()
        log_action(self.request, 'library.book_edit', target=b,
                   description=f"Kitob tahrirlandi: {b.title}")

    def perform_destroy(self, instance):
        log_action(self.request, 'library.book_delete', target=instance,
                   description=f"Kitob o'chirildi: {instance.title}")
        instance.delete()


class BookRentalListCreateView(generics.ListCreateAPIView):
    serializer_class = BookRentalSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [p() for p in _perm('library.rental_add')]
        return [p() for p in _perm('library.view')]

    def get_queryset(self):
        qs = BookRental.objects.select_related('book', 'student').all()
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    def perform_create(self, serializer):
        rental = serializer.save(given_by=self.request.user)
        if rental.book.available_copies > 0:
            rental.book.available_copies -= 1
            rental.book.save(update_fields=['available_copies'])
        log_action(self.request, 'library.rental_add', target=rental,
                   description=f"Kitob berildi: {rental.book.title} -> {rental.student.full_name}")


@api_view(['POST'])
@permission_classes(_perm('library.rental_return'))
def book_rental_return(request, pk):
    rental = get_object_or_404(BookRental, pk=pk)
    if rental.status == 'returned':
        return Response({'error': "Bu kitob allaqachon qaytarilgan"}, status=400)
    rental.mark_returned(request.user)
    log_action(request, 'library.rental_return', target=rental,
               description=f"Kitob qaytarildi: {rental.book.title}")
    return Response(BookRentalSerializer(rental).data)


# ============================================================
# 4) SUPPORT
# ============================================================

class HelpRequestListView(generics.ListAPIView):
    serializer_class = HelpRequestSerializer
    permission_classes = _perm('help_requests.view')

    def get_queryset(self):
        qs = HelpRequest.objects.select_related('user').all()
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        return qs


class HelpRequestDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = HelpRequestSerializer
    queryset = HelpRequest.objects.all()

    def get_permissions(self):
        m = self.request.method
        if m == 'DELETE':
            return [p() for p in _perm('help_requests.delete')]
        if m in ('PUT', 'PATCH'):
            return [p() for p in _perm('help_requests.respond')]
        return [p() for p in _perm('help_requests.view')]

    def perform_destroy(self, instance):
        log_action(self.request, 'help_requests.delete', target=instance,
                   description=f"Yordam xati o'chirildi: #{instance.id}")
        instance.delete()


@api_view(['POST'])
@permission_classes(_perm('help_requests.respond'))
def help_request_respond(request, pk):
    req = get_object_or_404(HelpRequest, pk=pk)
    response_text = request.data.get('admin_response')
    new_status = request.data.get('status')
    if response_text is not None:
        req.admin_response = response_text
    if new_status in ('pending', 'in_progress', 'resolved', 'closed'):
        req.status = new_status
    req.save()
    log_action(request, 'help_requests.respond', target=req,
               description=f"Yordam xatiga javob: #{req.id} ({req.status})")
    return Response(HelpRequestSerializer(req).data)


class CourseApplicationListView(generics.ListAPIView):
    serializer_class = CourseApplicationSerializer
    permission_classes = _perm('applications.view')

    def get_queryset(self):
        qs = CourseApplication.objects.filter(is_shaharcha=False)
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        return qs


class CourseApplicationDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CourseApplicationSerializer
    queryset = CourseApplication.objects.filter(is_shaharcha=False)

    def get_permissions(self):
        m = self.request.method
        if m == 'DELETE':
            return [p() for p in _perm('applications.delete')]
        if m in ('PUT', 'PATCH'):
            return [p() for p in _perm('applications.edit')]
        return [p() for p in _perm('applications.view')]

    def perform_update(self, serializer):
        app = serializer.save()
        log_action(self.request, 'applications.edit', target=app,
                   description=f"Ariza yangilandi: #{app.id} ({app.status})")

    def perform_destroy(self, instance):
        log_action(self.request, 'applications.delete', target=instance,
                   description=f"Ariza o'chirildi: #{instance.id}")
        instance.delete()


# ---- So'rovnomalar ----

class SurveyFormListCreateView(generics.ListCreateAPIView):
    serializer_class = SurveyFormSerializer
    queryset = SurveyForm.objects.all()

    def get_permissions(self):
        if self.request.method == 'POST':
            return [p() for p in _perm('surveys.add')]
        return [p() for p in _perm('surveys.view')]

    def perform_create(self, serializer):
        s = serializer.save()
        log_action(self.request, 'surveys.add', target=s,
                   description=f"So'rovnoma yaratildi: {s.title}")


class SurveyFormDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SurveyFormSerializer
    queryset = SurveyForm.objects.all()

    def get_permissions(self):
        m = self.request.method
        if m == 'DELETE':
            return [p() for p in _perm('surveys.delete')]
        if m in ('PUT', 'PATCH'):
            return [p() for p in _perm('surveys.edit')]
        return [p() for p in _perm('surveys.view')]

    def perform_update(self, serializer):
        s = serializer.save()
        log_action(self.request, 'surveys.edit', target=s,
                   description=f"So'rovnoma tahrirlandi: {s.title}")

    def perform_destroy(self, instance):
        log_action(self.request, 'surveys.delete', target=instance,
                   description=f"So'rovnoma o'chirildi: {instance.title}")
        instance.delete()


class SurveyQuestionListCreateView(generics.ListCreateAPIView):
    serializer_class = SurveyQuestionSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [p() for p in _perm('surveys.edit')]
        return [p() for p in _perm('surveys.view')]

    def get_queryset(self):
        qs = SurveyQuestion.objects.all()
        survey_id = self.request.query_params.get('survey')
        if survey_id:
            qs = qs.filter(survey_id=survey_id)
        return qs


class SurveyQuestionDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SurveyQuestionSerializer
    queryset = SurveyQuestion.objects.all()

    def get_permissions(self):
        m = self.request.method
        if m == 'DELETE':
            return [p() for p in _perm('surveys.edit')]
        if m in ('PUT', 'PATCH'):
            return [p() for p in _perm('surveys.edit')]
        return [p() for p in _perm('surveys.view')]


class SurveyResponseListView(generics.ListAPIView):
    serializer_class = SurveyResponseSerializer
    permission_classes = _perm('surveys.view')

    def get_queryset(self):
        qs = SurveyResponse.objects.select_related('user', 'survey').all()
        survey_id = self.request.query_params.get('survey')
        if survey_id:
            qs = qs.filter(survey_id=survey_id)
        return qs
