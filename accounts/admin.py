from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import (
    CustomUser, Profession, CourseEnrollment, Lesson, VideoLesson, VideoProgress,
    Homework, HomeworkSubmission, Test, TestQuestion, TestAnswer, TestResult,
    Certificate, Message, PaymentStatus, LoginAttempt, FinalTestPayment
)
from teacher.models import TeacherSalary, TeacherAttendance


class TeacherSalaryInline(admin.TabularInline):
    model = TeacherSalary
    fk_name = 'teacher'
    extra = 1
    fields = ['salary_type', 'amount', 'month', 'year', 'description', 'receipt', 'is_paid', 'paid_date']
    readonly_fields = ['created_by']


class TeacherAttendanceInline(admin.TabularInline):
    model = TeacherAttendance
    fk_name = 'teacher'
    extra = 1
    fields = ['date', 'status', 'check_in_time', 'check_out_time', 'notes']
    readonly_fields = ['created_by']


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ['student_id_display', 'username', 'full_name', 'phone', 'role', 'coins', 'is_blocked', 'is_online_display', 'date_joined']
    list_filter = ['role', 'is_blocked', 'profession', 'date_joined']
    search_fields = ['username', 'first_name', 'last_name', 'phone', 'student_id']
    ordering = ['-date_joined']
    list_editable = ['is_blocked']
    list_per_page = 25
    autocomplete_fields = ['profession']
    filter_horizontal = ['teaching_professions', 'groups', 'user_permissions']
    
    def get_inlines(self, request, obj=None):
        if obj and obj.role == 'teacher':
            return [TeacherSalaryInline, TeacherAttendanceInline]
        return []
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('profession').prefetch_related(
            'teaching_professions', 'groups'
        )
    
    fieldsets = (
        (None, {
            'fields': ('username', 'password'),
        }),
        ('Shaxsiy ma\'lumotlar', {
            'fields': (
                'first_name', 'last_name', 'phone', 'email', 'photo', 'bio',
                'gender', 'birth_date', 'nationality', 'address',
            ),
            'description': 'Foydalanuvchining asosiy shaxsiy ma\'lumotlari',
        }),
        ("O'quvchi ID", {
            'fields': ('student_id',),
            'description': "Avtomatik berilgan o'zgarmas 5 xonali ID raqam (Payme/Click to'lovlari uchun)",
        }),
        ('Rol va yo\'nalish', {
            'fields': (
                'role', 'profession', 'teaching_professions', 'coins',
                'is_premium', 'premium_purchased_at', 'premium_expires_at',
            ),
            'description': 'Foydalanuvchi roli, yo\'nalishi va coin balansi',
        }),
        ('Ota-ona ma\'lumotlari', {
            'fields': (
                'father_name', 'father_phone', 'father_deceased',
                'mother_name', 'mother_phone', 'mother_deceased',
                'parent_phone',
            ),
            'classes': ('collapse',),
        }),
        ('Hujjatlar', {
            'fields': (
                'passport_series', 'passport_number', 'passport_issued_date', 'jshshir',
                'id_card', 'birth_certificate',
                'school_name', 'school_number',
                'is_profile_completed',
            ),
            'classes': ('collapse',),
        }),
        ('Telegram', {
            'fields': ('telegram_id', 'telegram_username'),
        }),
        ('Status', {
            'fields': ('is_blocked', 'is_active', 'is_staff', 'is_superuser'),
        }),
        ('Vaqtlar', {
            'fields': (
                'last_activity', 'last_login', 'date_joined',
                'last_daily_login', 'total_online_time',
            ),
        }),
        ('Ruxsatlar', {
            'fields': ('groups', 'user_permissions'),
            'classes': ('collapse',),
        }),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'first_name', 'last_name', 'phone', 'role', 'password1', 'password2'),
        }),
    )
    
    readonly_fields = ['last_login', 'date_joined', 'last_activity', 'last_daily_login', 'total_online_time', 'student_id']

    def full_name(self, obj):
        return obj.full_name
    full_name.short_description = 'Ism Familiya'

    def is_online_display(self, obj):
        if obj.is_online:
            return format_html('<span style="color: #28a745;">●</span> Online')
        return format_html('<span style="color: #6c757d;">●</span> Offline')
    is_online_display.short_description = 'Status'

    def student_id_display(self, obj):
        if obj.student_id:
            return format_html(
                '<span style="'
                'background:#1e1b4b;color:#c4b5fd;'
                'padding:2px 8px;border-radius:6px;'
                'font-weight:700;font-size:0.85em;'
                'font-family:monospace;letter-spacing:1px;">'
                '#{}</span>',
                obj.student_id
            )
        return format_html('<span style="color:#9ca3af;">—</span>')
    student_id_display.short_description = 'ID'
    student_id_display.admin_order_field = 'student_id'


@admin.register(Profession)
class ProfessionAdmin(admin.ModelAdmin):
    list_display = ['name', 'student_count', 'teacher_count', 'lesson_count', 'daily_section_limit', 'created_at']
    list_editable = ['daily_section_limit']
    search_fields = ['name', 'description']
    list_per_page = 20
    
    def student_count(self, obj):
        count = obj.enrollments.filter(user__role='student').count()
        return format_html('<span class="badge bg-primary">{}</span>', count)
    student_count.short_description = "O'quvchilar"
    
    def teacher_count(self, obj):
        count = obj.students.filter(role='teacher').count()
        return format_html('<span class="badge bg-success">{}</span>', count)
    teacher_count.short_description = "O'qituvchilar"
    
    def lesson_count(self, obj):
        return obj.lessons.count()
    lesson_count.short_description = 'Darslar'


@admin.register(CourseEnrollment)
class CourseEnrollmentAdmin(admin.ModelAdmin):
    list_display = ['user', 'profession', 'enrolled_at']
    list_filter = ['profession', 'enrolled_at']
    search_fields = ['user__username', 'user__first_name', 'profession__name']
    autocomplete_fields = ['user', 'profession']
    date_hierarchy = 'enrolled_at'


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ['title', 'profession', 'lesson_type', 'has_article', 'created_by', 'created_at']
    list_filter = ['lesson_type', 'profession', 'created_at']
    search_fields = ['title', 'profession__name']
    autocomplete_fields = ['profession', 'created_by']

    fieldsets = (
        (None, {'fields': ('profession', 'section', 'title', 'lesson_type', 'order', 'created_by')}),
        ('AI maqola', {
            'classes': ('collapse',),
            'fields': ('ai_article',),
            'description': 'Video darslar uchun AI tomonidan yaratilgan maqola. O\'zgartirish mumkin.',
        }),
    )

    def has_article(self, obj):
        if obj.ai_article:
            return format_html('<span style="color:#28a745;">✓</span>')
        return format_html('<span style="color:#ccc;">—</span>')
    has_article.short_description = 'Maqola'


@admin.register(VideoLesson)
class VideoLessonAdmin(admin.ModelAdmin):
    list_display = ['lesson', 'duration', 'youtube_url', 'has_article']
    search_fields = ['lesson__title']

    def has_article(self, obj):
        if obj.lesson.ai_article:
            return format_html('<span style="color:#28a745;">✓ Bor</span>')
        return format_html('<span style="color:#dc3545;">✗ Yo\'q</span>')
    has_article.short_description = 'AI maqola'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)


@admin.register(Homework)
class HomeworkAdmin(admin.ModelAdmin):
    list_display = ['lesson', 'due_date']
    search_fields = ['lesson__title']


@admin.register(HomeworkSubmission)
class HomeworkSubmissionAdmin(admin.ModelAdmin):
    list_display = ['student', 'homework', 'status', 'grade', 'submitted_at']
    list_filter = ['status', 'submitted_at']
    search_fields = ['student__username', 'homework__lesson__title']
    list_editable = ['status', 'grade']


@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ['lesson', 'time_limit', 'passing_score', 'question_count']
    search_fields = ['lesson__title']
    
    def question_count(self, obj):
        return obj.questions.count()
    question_count.short_description = 'Savollar'


class TestAnswerInline(admin.TabularInline):
    model = TestAnswer
    extra = 3
    max_num = 4


@admin.register(TestQuestion)
class TestQuestionAdmin(admin.ModelAdmin):
    list_display = ['question_text_short', 'test', 'order']
    list_filter = ['test__lesson__profession']
    search_fields = ['question_text', 'test__lesson__title']
    inlines = [TestAnswerInline]
    
    def question_text_short(self, obj):
        return obj.question_text[:50] + '...' if len(obj.question_text) > 50 else obj.question_text
    question_text_short.short_description = 'Savol'


@admin.register(TestResult)
class TestResultAdmin(admin.ModelAdmin):
    list_display = ['student', 'test', 'score', 'passed', 'completed_at']
    list_filter = ['passed', 'completed_at', 'test__lesson__profession']
    search_fields = ['student__username', 'test__lesson__title']
    date_hierarchy = 'completed_at'
    
    def passed(self, obj):
        if obj.passed:
            return format_html('<span style="color: #28a745;">✓ O\'tdi</span>')
        return format_html('<span style="color: #dc3545;">✗ O\'tmadi</span>')
    passed.short_description = 'Natija'


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ['certificate_id', 'student', 'profession', 'status', 'valid_from', 'valid_until', 'issued_by', 'issued_at']
    list_filter = ['status', 'profession', 'issued_at']
    search_fields = ['certificate_id', 'student__username', 'student__first_name', 'student__last_name', 'profession__name']
    autocomplete_fields = ['student', 'profession', 'issued_by']
    list_editable = ['status']
    date_hierarchy = 'issued_at'
    readonly_fields = ['certificate_id', 'issued_at']


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['title', 'message_type', 'recipient', 'sender', 'is_read', 'created_at']
    list_filter = ['message_type', 'is_read', 'created_at']
    search_fields = ['title', 'content', 'recipient__username']
    date_hierarchy = 'created_at'


@admin.register(PaymentStatus)
class PaymentStatusAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_paid', 'last_payment_date', 'auto_blocked']
    list_filter = ['is_paid', 'auto_blocked']
    search_fields = ['user__username', 'user__first_name']
    list_editable = ['is_paid']


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ['ip_address', 'username', 'was_successful', 'attempted_at', 'user_agent_short']
    list_filter = ['was_successful', 'attempted_at']
    search_fields = ['ip_address', 'username']
    date_hierarchy = 'attempted_at'
    list_per_page = 50
    readonly_fields = ['ip_address', 'username', 'was_successful', 'attempted_at', 'user_agent']

    def user_agent_short(self, obj):
        return obj.user_agent[:80] + '...' if len(obj.user_agent) > 80 else obj.user_agent
    user_agent_short.short_description = 'User Agent'

    def has_add_permission(self, request):
        return False


@admin.register(FinalTestPayment)
class FinalTestPaymentAdmin(admin.ModelAdmin):
    list_display = ['student', 'test', 'amount', 'status', 'reviewed_by', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['student__username', 'student__first_name', 'test__lesson__title']
    list_editable = ['status']
    date_hierarchy = 'created_at'


# Admin site customization
admin.site.site_header = "LMS Admin Panel"
admin.site.site_title = "LMS"
admin.site.index_title = "Boshqaruv paneli"
