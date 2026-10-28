# Interactive Video Mid-Quiz System — boşlanğiç migratsiya

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0103_certificate_manual_recipient'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='VideoQuiz',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('trigger_second', models.PositiveIntegerField(help_text='Video şu soniyaga yetganda test çiqadi', verbose_name='Çiqiş vaqti (soniya)')),
                ('question', models.TextField(verbose_name='Savol')),
                ('description', models.TextField(blank=True, default='', verbose_name='Izoh (ixtiyoriy)')),
                ('option_a', models.CharField(max_length=300, verbose_name='A variant')),
                ('option_b', models.CharField(max_length=300, verbose_name='B variant')),
                ('option_c', models.CharField(max_length=300, verbose_name='C variant')),
                ('option_d', models.CharField(max_length=300, verbose_name='D variant')),
                ('correct_option', models.CharField(choices=[('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')], max_length=1, verbose_name="Töğri javob")),
                ('explanation', models.TextField(blank=True, default='', verbose_name="Tuşuntiriş (notöğri javobda körsatiladi)")),
                ('reward_coin', models.PositiveSmallIntegerField(default=3, verbose_name='Mukofot coin')),
                ('penalty_coin', models.PositiveSmallIntegerField(default=5, verbose_name='Jarima coin')),
                ('teacher_reward', models.PositiveIntegerField(default=3000, verbose_name="Ustoz mukofoti (söm)")),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='Faol')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='video_quizzes_created', to=settings.AUTH_USER_MODEL, verbose_name='Yaratgan ustoz')),
                ('video', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mid_quizzes', to='accounts.videolesson', verbose_name='Video dars')),
            ],
            options={
                'verbose_name': 'Video test',
                'verbose_name_plural': 'Video testlar',
                'ordering': ['trigger_second'],
            },
        ),
        migrations.CreateModel(
            name='TeacherVideoIncome',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.PositiveIntegerField(verbose_name="Miqdor (söm)")),
                ('note', models.CharField(blank=True, default='', max_length=300, verbose_name='Izoh')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('quiz', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='income_records', to='video_quiz.videoquiz', verbose_name='Test')),
                ('teacher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='video_quiz_incomes', to=settings.AUTH_USER_MODEL, verbose_name='Ustoz')),
            ],
            options={
                'verbose_name': 'Ustoz video daromadi',
                'verbose_name_plural': 'Ustoz video daromadlari',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='VideoQuizAttempt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('selected_option', models.CharField(choices=[('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')], max_length=1, verbose_name='Tanlangan javob')),
                ('is_correct', models.BooleanField(db_index=True, default=False, verbose_name="Töğri")),
                ('coins_change', models.IntegerField(default=0, verbose_name="Coin özgarişi")),
                ('answer_ms', models.PositiveIntegerField(default=0, help_text="Modal oçilgandan javobgaça ötgan vaqt", verbose_name='Javob vaqti (ms)')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('quiz', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attempts', to='video_quiz.videoquiz', verbose_name='Test')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='video_quiz_attempts', to=settings.AUTH_USER_MODEL, verbose_name="Öquvçi")),
            ],
            options={
                'verbose_name': 'Video test urinişi',
                'verbose_name_plural': 'Video test urinişlari',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='videoquiz',
            index=models.Index(fields=['video', 'is_active'], name='vq_video_active_idx'),
        ),
        migrations.AddIndex(
            model_name='videoquiz',
            index=models.Index(fields=['created_by', '-created_at'], name='vq_creator_created_idx'),
        ),
        migrations.AddConstraint(
            model_name='videoquiz',
            constraint=models.UniqueConstraint(fields=('video', 'trigger_second'), name='uniq_video_trigger_second'),
        ),
        migrations.AddIndex(
            model_name='teachervideoincome',
            index=models.Index(fields=['teacher', '-created_at'], name='vq_income_teacher_idx'),
        ),
        migrations.AddIndex(
            model_name='videoquizattempt',
            index=models.Index(fields=['student', '-created_at'], name='vq_att_student_idx'),
        ),
        migrations.AddIndex(
            model_name='videoquizattempt',
            index=models.Index(fields=['quiz', 'is_correct'], name='vq_att_quiz_correct_idx'),
        ),
        migrations.AddConstraint(
            model_name='videoquizattempt',
            constraint=models.UniqueConstraint(fields=('quiz', 'student'), name='uniq_quiz_student_attempt'),
        ),
    ]
