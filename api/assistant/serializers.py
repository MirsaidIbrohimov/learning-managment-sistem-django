from rest_framework import serializers

from accounts.models import (
    CustomUser, Profession, Lesson, Homework, HomeworkSubmission,
    Test, TestResult, Certificate,
    Message, HelpRequest, CourseApplication,
    PasswordResetRequest, Parent, ParentMessage, ParentPasswordResetRequest,
    CourseEnrollmentRequest, CourseUnenrollRequest, PremiumRequest,
    Book, BookRental, SurveyForm, SurveyQuestion, SurveyResponse, SurveyAnswer,
)
from blog.models import Post, PostComment
from teacher.models import TeacherAttendance


# ------------------- USERS -------------------

class AssistantUserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    profession_name = serializers.CharField(source='profession.name', read_only=True, default=None)

    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'full_name', 'first_name', 'last_name',
            'phone', 'email', 'role', 'photo',
            'birth_date', 'gender', 'nationality',
            'father_name', 'mother_name', 'parent_phone',
            'school_name', 'school_number', 'address',
            'profession', 'profession_name',
            'coins', 'is_premium', 'is_blocked', 'is_profile_completed',
            'telegram_username', 'date_joined', 'last_activity',
        ]
        read_only_fields = ['id', 'username', 'role', 'coins', 'is_premium', 'date_joined', 'last_activity']


# ------------------- VAZIFALAR (HOMEWORK) -------------------

class HomeworkSerializer(serializers.ModelSerializer):
    lesson_title = serializers.CharField(source='lesson.title', read_only=True)
    profession = serializers.CharField(source='lesson.profession.name', read_only=True)
    submissions_count = serializers.SerializerMethodField()

    class Meta:
        model = Homework
        fields = [
            'id', 'lesson', 'lesson_title', 'profession', 'description',
            'allowed_formats', 'due_date', 'max_score', 'late_penalty',
            'allow_late', 'ai_check', 'file_only', 'handwritten_only',
            'submissions_count',
        ]

    def get_submissions_count(self, obj):
        return obj.submissions.count()


class HomeworkSubmissionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    homework_title = serializers.CharField(source='homework.lesson.title', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = HomeworkSubmission
        fields = [
            'id', 'homework', 'homework_title', 'student', 'student_name',
            'submission_type', 'file', 'text_content', 'status', 'status_display',
            'grade', 'feedback', 'submitted_at', 'graded_at', 'is_late', 'version',
            'ai_feedback', 'ai_checked',
        ]


# ------------------- TEST HULOSALARI -------------------

class TestResultDetailSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    test_name = serializers.CharField(source='test.lesson.title', read_only=True)
    profession = serializers.CharField(source='test.lesson.profession.name', read_only=True)

    class Meta:
        model = TestResult
        fields = [
            'id', 'test', 'test_name', 'profession', 'student', 'student_name',
            'score', 'total_questions', 'correct_answers',
            'started_at', 'completed_at', 'passed',
        ]


# ------------------- DARSLAR TAHLILI -------------------

class LessonAnalyticsSerializer(serializers.ModelSerializer):
    profession_name = serializers.CharField(source='profession.name', read_only=True)
    section_title = serializers.CharField(source='section.title', read_only=True, default=None)
    test_attempts = serializers.SerializerMethodField()
    test_pass_rate = serializers.SerializerMethodField()
    avg_score = serializers.SerializerMethodField()
    homework_submissions = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = [
            'id', 'title', 'lesson_type', 'order',
            'profession', 'profession_name', 'section', 'section_title',
            'test_attempts', 'test_pass_rate', 'avg_score', 'homework_submissions',
        ]

    def get_test_attempts(self, obj):
        if hasattr(obj, 'test'):
            return obj.test.results.count()
        return 0

    def get_test_pass_rate(self, obj):
        if hasattr(obj, 'test'):
            total = obj.test.results.count()
            if total == 0:
                return 0
            passed = obj.test.results.filter(passed=True).count()
            return round((passed / total) * 100, 2)
        return 0

    def get_avg_score(self, obj):
        if hasattr(obj, 'test'):
            from django.db.models import Avg
            avg = obj.test.results.aggregate(a=Avg('score'))['a']
            return round(avg, 2) if avg else 0
        return 0

    def get_homework_submissions(self, obj):
        if hasattr(obj, 'homework'):
            return obj.homework.submissions.count()
        return 0


# ------------------- DAVOMAT -------------------

class TeacherAttendanceSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = TeacherAttendance
        fields = [
            'id', 'teacher', 'teacher_name', 'date', 'status', 'status_display',
            'check_in_time', 'check_out_time', 'notes',
            'created_at', 'updated_at',
        ]


# ------------------- SERTIFIKATLAR -------------------

class CertificateSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    profession_name = serializers.CharField(source='profession.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Certificate
        fields = [
            'id', 'certificate_id', 'student', 'student_name',
            'profession', 'profession_name',
            'status', 'status_display',
            'valid_from', 'valid_until', 'issued_at',
        ]
        read_only_fields = ['certificate_id', 'issued_at']


# ------------------- PAROL TIKLASH -------------------

class PasswordResetRequestSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    user_phone = serializers.CharField(source='user.phone', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = PasswordResetRequest
        fields = [
            'id', 'user', 'user_name', 'user_phone',
            'status', 'status_display', 'admin_message',
            'created_at', 'updated_at',
        ]


# ------------------- OTA-ONALAR -------------------

class ParentSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    children_count = serializers.SerializerMethodField()

    class Meta:
        model = Parent
        fields = [
            'id', 'first_name', 'last_name', 'full_name',
            'phone', 'email', 'username', 'is_active',
            'children_count', 'last_login', 'created_at',
        ]

    def get_children_count(self, obj):
        return obj.children.count()


class ParentMessageSerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source='parent.full_name', read_only=True)
    child_name = serializers.CharField(source='child.full_name', read_only=True)

    class Meta:
        model = ParentMessage
        fields = [
            'id', 'parent', 'parent_name', 'child', 'child_name',
            'subject', 'message', 'reply', 'replied_by', 'replied_at',
            'is_read', 'created_at',
        ]
        read_only_fields = ['replied_by', 'replied_at']


class ParentPasswordResetRequestSerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source='parent.full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ParentPasswordResetRequest
        fields = [
            'id', 'parent', 'parent_name',
            'status', 'status_display',
            'reviewed_by', 'reviewed_at', 'created_at',
        ]


# ------------------- SO'ROVLAR (REQUESTS) -------------------

class CourseEnrollmentRequestSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    profession_name = serializers.CharField(source='profession.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = CourseEnrollmentRequest
        fields = '__all__'


class CourseUnenrollRequestSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    profession_name = serializers.CharField(source='profession.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = CourseUnenrollRequest
        fields = '__all__'


class PremiumRequestSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    plan_display = serializers.CharField(source='get_plan_display', read_only=True)

    class Meta:
        model = PremiumRequest
        fields = '__all__'


# ------------------- XABARLAR -------------------

class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.full_name', read_only=True)
    recipient_name = serializers.CharField(source='recipient.full_name', read_only=True, default=None)
    message_type_display = serializers.CharField(source='get_message_type_display', read_only=True)

    class Meta:
        model = Message
        fields = [
            'id', 'title', 'content', 'message_type', 'message_type_display',
            'recipient', 'recipient_name', 'sender', 'sender_name',
            'is_read', 'created_at',
        ]
        read_only_fields = ['sender', 'is_read', 'created_at']


# ------------------- BLOG -------------------

class BlogPostSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.full_name', read_only=True)
    likes_count = serializers.IntegerField(read_only=True)
    comments_count = serializers.IntegerField(read_only=True)
    post_type_display = serializers.CharField(source='get_post_type_display', read_only=True)

    class Meta:
        model = Post
        fields = [
            'id', 'title', 'content', 'image', 'post_type', 'post_type_display',
            'author', 'author_name', 'is_published',
            'likes_count', 'comments_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['author', 'created_at', 'updated_at']


class BlogCommentSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    post_title = serializers.CharField(source='post.title', read_only=True)

    class Meta:
        model = PostComment
        fields = ['id', 'post', 'post_title', 'user', 'user_name', 'content', 'created_at']


# ------------------- KUTUBXONA -------------------

class BookSerializer(serializers.ModelSerializer):
    is_available = serializers.BooleanField(read_only=True)

    class Meta:
        model = Book
        fields = [
            'id', 'title', 'author', 'isbn', 'description', 'cover_image',
            'total_copies', 'available_copies', 'is_available', 'created_at',
        ]


class BookRentalSerializer(serializers.ModelSerializer):
    book_title = serializers.CharField(source='book.title', read_only=True)
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    days_until_return = serializers.IntegerField(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = BookRental
        fields = [
            'id', 'book', 'book_title', 'student', 'student_name',
            'given_by', 'given_date', 'return_date', 'actual_return_date',
            'returned_to', 'status', 'status_display', 'notes',
            'is_overdue', 'days_until_return',
            'created_at', 'updated_at',
        ]


# ------------------- YORDAM XATLARI -------------------

class HelpRequestSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    user_phone = serializers.CharField(source='user.phone', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = HelpRequest
        fields = [
            'id', 'user', 'user_name', 'user_phone',
            'subject', 'message', 'image',
            'status', 'status_display', 'admin_response',
            'created_at', 'updated_at',
        ]


# ------------------- ARIZALAR -------------------

class CourseApplicationSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = CourseApplication
        fields = [
            'id', 'first_name', 'last_name', 'phone',
            'course_interest', 'status', 'status_display', 'admin_note',
            'created_at',
        ]


# ------------------- SO'ROVNOMALAR -------------------

class SurveyQuestionSerializer(serializers.ModelSerializer):
    choices_list = serializers.SerializerMethodField()
    question_type_display = serializers.CharField(source='get_question_type_display', read_only=True)

    class Meta:
        model = SurveyQuestion
        fields = [
            'id', 'survey', 'question_text', 'question_type', 'question_type_display',
            'choices', 'choices_list', 'is_required', 'order',
        ]

    def get_choices_list(self, obj):
        return obj.get_choices_list()


class SurveyFormSerializer(serializers.ModelSerializer):
    question_count = serializers.IntegerField(read_only=True)
    response_count = serializers.IntegerField(read_only=True)
    target_role_display = serializers.CharField(source='get_target_role_display', read_only=True)

    class Meta:
        model = SurveyForm
        fields = [
            'id', 'title', 'description', 'is_active', 'show_on_login',
            'is_required', 'target_role', 'target_role_display',
            'question_count', 'response_count',
            'created_at', 'updated_at',
        ]


class SurveyResponseSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    survey_title = serializers.CharField(source='survey.title', read_only=True)

    class Meta:
        model = SurveyResponse
        fields = ['id', 'survey', 'survey_title', 'user', 'user_name', 'submitted_at']
