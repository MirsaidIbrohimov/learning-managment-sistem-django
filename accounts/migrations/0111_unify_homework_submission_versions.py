from django.db import migrations, models
from django.db.models import Count


def unify_homework_submission_versions(apps, schema_editor):
    HomeworkSubmission = apps.get_model('accounts', 'HomeworkSubmission')
    HomeworkRevision = apps.get_model('accounts', 'HomeworkRevision')
    HomeworkMessage = apps.get_model('accounts', 'HomeworkMessage')

    duplicate_groups = HomeworkSubmission.objects.values(
        'homework_id', 'student_id'
    ).annotate(total=Count('id')).filter(total__gt=1)

    for group in duplicate_groups.iterator():
        submissions = list(HomeworkSubmission.objects.filter(
            homework_id=group['homework_id'],
            student_id=group['student_id'],
        ).order_by('submitted_at', 'pk'))
        canonical = submissions[-1]

        coin_awarded = any(item.coin_awarded for item in submissions)
        coins_earned = max((item.coins_earned for item in submissions), default=0)

        for old in submissions[:-1]:
            revision = HomeworkRevision.objects.create(
                submission_id=canonical.pk,
                file=old.file or None,
                text_content=old.text_content or '',
                submission_type=old.submission_type,
                status=old.status,
                grade=old.grade,
                feedback=old.feedback or '',
                note=f"Versiya {old.version}",
            )
            HomeworkRevision.objects.filter(pk=revision.pk).update(
                submitted_at=old.submitted_at,
            )
            HomeworkRevision.objects.filter(submission_id=old.pk).update(
                submission_id=canonical.pk,
            )
            HomeworkMessage.objects.filter(submission_id=old.pk).update(
                submission_id=canonical.pk,
            )
            old.delete()

        revision_count = HomeworkRevision.objects.filter(
            submission_id=canonical.pk
        ).count()
        canonical.version = max(canonical.version, revision_count + 1)
        canonical.revision_count = canonical.version - 1
        canonical.coin_awarded = coin_awarded
        canonical.coins_earned = coins_earned
        canonical.save(update_fields=[
            'version', 'revision_count', 'coin_awarded', 'coins_earned'
        ])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0110_clean_contract_unpaid_records'),
    ]

    operations = [
        migrations.AlterField(
            model_name='homeworkrevision',
            name='file',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='homework_revisions/',
            ),
        ),
        migrations.AddField(
            model_name='homeworkrevision',
            name='feedback',
            field=models.TextField(blank=True, default='', verbose_name="Öşa paytdagi izoh"),
        ),
        migrations.AddField(
            model_name='homeworkrevision',
            name='grade',
            field=models.IntegerField(blank=True, null=True, verbose_name="Öşa paytdagi baho"),
        ),
        migrations.AddField(
            model_name='homeworkrevision',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Kutilmoqda'),
                    ('reviewing', "Körib çiqilmoqda"),
                    ('revision', 'Qayta işlaş kerak'),
                    ('accepted', 'Qabul qilindi'),
                    ('graded', 'Baholangan'),
                ],
                default='pending',
                max_length=20,
                verbose_name="Öşa paytdagi holat",
            ),
        ),
        migrations.AddField(
            model_name='homeworkrevision',
            name='submission_type',
            field=models.CharField(
                choices=[('file', 'Fayl'), ('text', 'Matn')],
                default='file',
                max_length=10,
                verbose_name='Topşiriş turi',
            ),
        ),
        migrations.AddField(
            model_name='homeworkrevision',
            name='text_content',
            field=models.TextField(blank=True, default='', verbose_name='Matn javobi'),
        ),
        migrations.RunPython(
            unify_homework_submission_versions,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='homeworksubmission',
            constraint=models.UniqueConstraint(
                fields=('homework', 'student'),
                name='unique_homework_submission_per_student',
            ),
        ),
    ]
