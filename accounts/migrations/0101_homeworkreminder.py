# HomeworkReminder — avtomatik vazifa eslatmalari holati

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0100_courseapplication_handled_at_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='HomeworkReminder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('teacher_level', models.PositiveSmallIntegerField(default=0, verbose_name='Ustozga yuborilgan bildirishnoma darajasi')),
                ('last_teacher_sent', models.DateTimeField(blank=True, null=True, verbose_name='Ustozga oxirgi yuborilgan vaqt')),
                ('group_notified_at', models.DateTimeField(blank=True, null=True, verbose_name='Guruhga yuborilgan vaqt')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('submission', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='reminder_state', to='accounts.homeworksubmission', verbose_name="Vazifa topshirig'i")),
            ],
            options={
                'verbose_name': 'Vazifa eslatmasi',
                'verbose_name_plural': 'Vazifa eslatmalari',
                'indexes': [models.Index(fields=['teacher_level'], name='accounts_ho_teacher_idx01')],
            },
        ),
    ]
