from rest_framework import serializers
from accounts.models import CustomUser, Profession, Section, CourseEnrollment, Lesson, VideoLesson, Homework, HomeworkSubmission, Test, TestResult, Certificate


class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    profile_completion_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'first_name', 'last_name', 'full_name',
            'role', 'photo', 'bio',
            'birth_date', 'gender', 'nationality',
            'school_name', 'school_number', 'address',
            'coins', 'is_premium', 'is_profile_completed',
            'profile_completion_percent', 'date_joined', 'last_activity',
        ]
        read_only_fields = ['id', 'username', 'role', 'coins', 'is_premium', 'date_joined', 'last_activity']


class ProfileCompleteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = [
            'first_name', 'last_name', 'birth_date', 'gender', 'nationality',
            'father_name', 'mother_name', 'parent_phone',
            'school_name', 'school_number', 'address',
            'id_card', 'birth_certificate',
        ]

    def validate(self, data):
        instance = self.instance
        # Merge with existing data for validation
        first_name = data.get('first_name', getattr(instance, 'first_name', ''))
        last_name = data.get('last_name', getattr(instance, 'last_name', ''))
        birth_date = data.get('birth_date', getattr(instance, 'birth_date', None))
        gender = data.get('gender', getattr(instance, 'gender', ''))
        nationality = data.get('nationality', getattr(instance, 'nationality', ''))
        father_name = data.get('father_name', getattr(instance, 'father_name', ''))
        mother_name = data.get('mother_name', getattr(instance, 'mother_name', ''))
        parent_phone = data.get('parent_phone', getattr(instance, 'parent_phone', ''))
        school_name = data.get('school_name', getattr(instance, 'school_name', ''))
        school_number = data.get('school_number', getattr(instance, 'school_number', ''))
        address = data.get('address', getattr(instance, 'address', ''))

        required_fields = [first_name, last_name, birth_date, gender, nationality,
                          father_name, mother_name, parent_phone, school_name, school_number, address]

        if not all(required_fields):
            raise serializers.ValidationError("Barça majburiy maydonlarni töldiring.")

        id_card = data.get('id_card', getattr(instance, 'id_card', None))
        birth_certificate = data.get('birth_certificate', getattr(instance, 'birth_certificate', None))

        if not id_card and not birth_certificate:
            raise serializers.ValidationError("Pasport yoki tuğilganlik guvohnomasidan kamida bittasini yuklang.")

        return data


class ProfessionListSerializer(serializers.ModelSerializer):
    student_count = serializers.SerializerMethodField()

    class Meta:
        model = Profession
        fields = ['id', 'name', 'photo', 'description', 'is_paid', 'is_mandatory', 'is_blocked', 'student_count', 'created_at']

    def get_student_count(self, obj):
        return obj.enrollments.filter(user__role='student').count()


class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ['id', 'title', 'description', 'order', 'is_active']


class LessonSerializer(serializers.ModelSerializer):
    section_title = serializers.CharField(source='section.title', read_only=True, default=None)

    class Meta:
        model = Lesson
        fields = ['id', 'title', 'lesson_type', 'order', 'section', 'section_title', 'created_at']


class EnrollmentSerializer(serializers.ModelSerializer):
    profession = ProfessionListSerializer(read_only=True)

    class Meta:
        model = CourseEnrollment
        fields = ['id', 'profession', 'enrolled_at']


class TestResultSerializer(serializers.ModelSerializer):
    test_name = serializers.CharField(source='test.lesson.title', read_only=True)

    class Meta:
        model = TestResult
        fields = ['id', 'test_name', 'score', 'total_questions', 'correct_answers', 'passed', 'completed_at']


class CertificateSerializer(serializers.ModelSerializer):
    profession_name = serializers.CharField(source='profession.name', read_only=True)

    class Meta:
        model = Certificate
        fields = ['id', 'certificate_id', 'profession_name', 'status', 'file', 'valid_from', 'valid_until', 'issued_at']


class StudentListSerializer(serializers.ModelSerializer):
    """Admin uçun öquvçilar röyxati — faqat admin foydalanuvçilariga oçiq"""
    full_name = serializers.CharField(read_only=True)
    profession_name = serializers.CharField(source='profession.name', read_only=True, default=None)

    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'full_name', 'first_name', 'last_name',
            'phone', 'email', 'role', 'birth_date', 'gender', 'nationality',
            'father_name', 'mother_name', 'parent_phone',
            'school_name', 'school_number', 'address',
            'profession_name', 'coins', 'is_premium', 'is_blocked',
            'is_profile_completed', 'telegram_username',
            'date_joined', 'last_activity',
        ]
