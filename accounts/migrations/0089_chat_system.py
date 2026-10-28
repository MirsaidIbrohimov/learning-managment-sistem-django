from django.conf import settings
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('accounts', '0088_profession_kind_topic_count_duration'),
    ]

    operations = [
        migrations.CreateModel(
            name='GroupChatMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message', models.TextField(blank=True, verbose_name='Xabar')),
                ('file', models.FileField(blank=True, null=True, upload_to='group_chat/', verbose_name='Fayl')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('is_deleted', models.BooleanField(default=False, verbose_name="Öçirilgan")),
                ('profession', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chat_messages', to='accounts.profession', verbose_name='Guruh (kurs)')),
                ('sender', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='group_chat_messages', to=settings.AUTH_USER_MODEL, verbose_name='Yuboruvçi')),
            ],
            options={
                'verbose_name': 'Guruh çat xabari',
                'verbose_name_plural': 'Guruh çat xabarlari',
                'ordering': ['created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='groupchatmessage',
            index=models.Index(fields=['profession', 'created_at'], name='accounts_gc_prof_created_idx'),
        ),
        migrations.CreateModel(
            name='GroupChatRead',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('last_read_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('profession', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chat_reads', to='accounts.profession')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='group_chat_reads', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': "Guruh çat öqilgan holati",
                'verbose_name_plural': "Guruh çat öqilgan holatlari",
                'unique_together': {('profession', 'user')},
            },
        ),
        migrations.CreateModel(
            name='DirectMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message', models.TextField(blank=True, verbose_name='Xabar')),
                ('file', models.FileField(blank=True, null=True, upload_to='direct_chat/', verbose_name='Fayl')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('is_read', models.BooleanField(default=False, verbose_name="Öqilgan")),
                ('is_deleted', models.BooleanField(default=False, verbose_name="Öçirilgan")),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='received_direct_messages', to=settings.AUTH_USER_MODEL, verbose_name='Qabul qiluvçi')),
                ('sender', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sent_direct_messages', to=settings.AUTH_USER_MODEL, verbose_name='Yuboruvçi')),
            ],
            options={
                'verbose_name': 'Şaxsiy xabar',
                'verbose_name_plural': 'Şaxsiy xabarlar',
                'ordering': ['created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='directmessage',
            index=models.Index(fields=['sender', 'recipient', 'created_at'], name='accounts_dm_thread_idx'),
        ),
        migrations.AddIndex(
            model_name='directmessage',
            index=models.Index(fields=['recipient', 'is_read'], name='accounts_dm_unread_idx'),
        ),
    ]
