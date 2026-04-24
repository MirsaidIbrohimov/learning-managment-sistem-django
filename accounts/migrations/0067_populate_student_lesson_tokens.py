import uuid
from django.db import migrations


def populate_tokens(apps, schema_editor):
    CourseEnrollment = apps.get_model('accounts', 'CourseEnrollment')
    Lesson = apps.get_model('accounts', 'Lesson')
    StudentLessonToken = apps.get_model('accounts', 'StudentLessonToken')

    for enrollment in CourseEnrollment.objects.all().select_related('user', 'profession'):
        lesson_ids = list(
            Lesson.objects.filter(profession=enrollment.profession).values_list('id', flat=True)
        )
        existing_ids = set(
            StudentLessonToken.objects.filter(
                student=enrollment.user, lesson_id__in=lesson_ids
            ).values_list('lesson_id', flat=True)
        )
        objs = [
            StudentLessonToken(student=enrollment.user, lesson_id=lid, token=uuid.uuid4())
            for lid in lesson_ids if lid not in existing_ids
        ]
        if objs:
            StudentLessonToken.objects.bulk_create(objs, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0066_student_lesson_token'),
    ]

    operations = [
        migrations.RunPython(populate_tokens, migrations.RunPython.noop),
    ]
