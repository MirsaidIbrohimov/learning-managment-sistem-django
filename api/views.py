from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from accounts.models import CustomUser, Profession, Section, CourseEnrollment, Lesson, TestResult, Certificate

from .serializers import (
    UserProfileSerializer, ProfileCompleteSerializer, ProfessionListSerializer,
    SectionSerializer, LessonSerializer, EnrollmentSerializer,
    TestResultSerializer, CertificateSerializer, StudentListSerializer,
)
from .permissions import IsAdmin, IsTeacher, IsProfileCompleted


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class ProfileCompleteView(generics.UpdateAPIView):
    serializer_class = ProfileCompleteSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def perform_update(self, serializer):
        user = serializer.save()
        if user.check_profile_completed():
            user.is_profile_completed = True
            user.save(update_fields=['is_profile_completed'])


class ProfessionListView(generics.ListAPIView):
    serializer_class = ProfessionListSerializer
    permission_classes = [IsAuthenticated, IsProfileCompleted]

    def get_queryset(self):
        qs = Profession.objects.all()
        if self.request.user.role == 'student':
            qs = qs.filter(is_blocked=False)
        return qs


class ProfessionDetailView(generics.RetrieveAPIView):
    serializer_class = ProfessionListSerializer
    permission_classes = [IsAuthenticated, IsProfileCompleted]
    queryset = Profession.objects.all()


class CourseSectionsView(generics.ListAPIView):
    serializer_class = SectionSerializer
    permission_classes = [IsAuthenticated, IsProfileCompleted]

    def get_queryset(self):
        return Section.objects.filter(profession_id=self.kwargs['pk'], is_active=True)


class CourseLessonsView(generics.ListAPIView):
    serializer_class = LessonSerializer
    permission_classes = [IsAuthenticated, IsProfileCompleted]

    def get_queryset(self):
        return Lesson.objects.filter(profession_id=self.kwargs['pk']).select_related('section')


class MyEnrollmentsView(generics.ListAPIView):
    serializer_class = EnrollmentSerializer
    permission_classes = [IsAuthenticated, IsProfileCompleted]

    def get_queryset(self):
        return CourseEnrollment.objects.filter(user=self.request.user).select_related('profession')


class MyTestResultsView(generics.ListAPIView):
    serializer_class = TestResultSerializer
    permission_classes = [IsAuthenticated, IsProfileCompleted]

    def get_queryset(self):
        return TestResult.objects.filter(student=self.request.user).select_related('test__lesson').order_by('-completed_at')


class MyCertificatesView(generics.ListAPIView):
    serializer_class = CertificateSerializer
    permission_classes = [IsAuthenticated, IsProfileCompleted]

    def get_queryset(self):
        return Certificate.objects.filter(student=self.request.user).select_related('profession')


class AdminStudentListView(generics.ListAPIView):
    serializer_class = StudentListSerializer
    permission_classes = [IsAuthenticated, IsAdmin]

    def get_queryset(self):
        qs = CustomUser.objects.filter(role='student').select_related('profession').order_by('-date_joined')
        search = self.request.query_params.get('search', '')
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(first_name__icontains=search) | Q(last_name__icontains=search) |
                Q(username__icontains=search) | Q(phone__icontains=search)
            )
        profession_id = self.request.query_params.get('profession')
        if profession_id:
            qs = qs.filter(profession_id=profession_id)
        return qs


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_status(request):
    return Response({
        'status': 'ok',
        'user': request.user.username,
        'role': request.user.role,
        'is_profile_completed': request.user.is_profile_completed,
        'server_time': timezone.now().isoformat(),
    })



