# Ustoz daromadini VIDEO bo'yicha bir martalik qilish (>=5 test) + qayta hisoblash.
#
# Oldin:  har bir test qo'shilganda 3000 so'm yozilardi (5 test = 15 000 so'm).
# Endi:   ustoz bitta videoga kamida 5 ta test qo'shsa, 3000 so'm BIR MARTA.
#
# Ushbu migratsiya:
#   1) TeacherVideoIncome ga `video` FK qo'shadi;
#   2) eski (har test uchun) yozuvlarni o'chirib, yangi qoidaga ko'ra qayta yozadi;
#   3) (teacher, video) unikal cheklovini qo'yadi (bir videoga ikki daromad bo'lmaydi).

import django.db.models.deletion
from django.db import migrations, models

# Qoida parametrlari — views.py dagi qiymatlar bilan mos bo'lishi shart
MIN_QUIZZES = 5
AMOUNT = 3000
RECALC_NOTE = "Video uchun 5+ test (qayta hisoblangan)"


def recalc_income(apps, schema_editor):
    """Eski per-test daromadni yangi per-video qoidaga ko'ra qayta hisoblaydi."""
    from django.db.models import Count

    VideoQuiz = apps.get_model('video_quiz', 'VideoQuiz')
    TeacherVideoIncome = apps.get_model('video_quiz', 'TeacherVideoIncome')
    User = apps.get_model('accounts', 'CustomUser')

    # 1) Eski (har test uchun) daromad yozuvlarini butunlay olib tashlaymiz
    TeacherVideoIncome.objects.all().delete()

    # 2) Faqat 'teacher' rolidagi foydalanuvchilar daromad oladi
    teacher_ids = list(User.objects.filter(role='teacher').values_list('id', flat=True))
    if not teacher_ids:
        return

    # 3) (ustoz, video) bo'yicha ustozning o'z testlari >=5 bo'lsa — bir marta 3000 so'm
    groups = (
        VideoQuiz.objects
        .filter(created_by_id__in=teacher_ids, video__isnull=False)
        .values('created_by', 'video')
        .annotate(c=Count('id'))
        .filter(c__gte=MIN_QUIZZES)
    )
    rows = [
        TeacherVideoIncome(
            teacher_id=g['created_by'],
            video_id=g['video'],
            quiz=None,
            amount=AMOUNT,
            note=RECALC_NOTE,
        )
        for g in groups
    ]
    if rows:
        TeacherVideoIncome.objects.bulk_create(rows)


def undo_recalc(apps, schema_editor):
    """Ortga qaytarish (best-effort): qayta hisoblangan yozuvlarni o'chiradi."""
    TeacherVideoIncome = apps.get_model('video_quiz', 'TeacherVideoIncome')
    TeacherVideoIncome.objects.filter(note=RECALC_NOTE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0103_certificate_manual_recipient'),
        ('video_quiz', '0001_initial'),
    ]

    operations = [
        # 1) `video` FK — daromadning asosiy bog'lanishi
        migrations.AddField(
            model_name='teachervideoincome',
            name='video',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='teacher_incomes',
                to='accounts.videolesson',
                verbose_name='Video dars',
            ),
        ),
        # 2) Ma'lumotni yangi qoidaga ko'ra qayta hisoblash
        migrations.RunPython(recalc_income, undo_recalc),
        # 3) Bir ustoz + bir video uchun faqat bitta daromad yozuvi
        migrations.AddConstraint(
            model_name='teachervideoincome',
            constraint=models.UniqueConstraint(
                fields=('teacher', 'video'), name='uniq_teacher_video_income'
            ),
        ),
    ]


# Bu fayl: daromad modelini "har test" dan "har video (bir marta, >=5 test)" ga
# o'tkazadi va mavjud ma'lumotni yangi qoida bo'yicha xavfsiz qayta hisoblaydi.
