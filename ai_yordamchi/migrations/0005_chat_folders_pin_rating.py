from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('ai_yordamchi', '0004_chatmessage_file_chatmessage_file_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChatFolder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='Nomi')),
                ('color', models.CharField(default='#6366f1', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chat_folders', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Papka',
                'verbose_name_plural': 'Papkalar',
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='chatsession',
            name='is_pinned',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='chatmessage',
            name='rating',
            field=models.SmallIntegerField(blank=True, help_text='1 = foydali, -1 = foydasiz', null=True),
        ),
        migrations.AddField(
            model_name='chatsession',
            name='folder',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sessions', to='ai_yordamchi.chatfolder'),
        ),
        migrations.AlterModelOptions(
            name='chatsession',
            options={'ordering': ['-is_pinned', '-updated_at'], 'verbose_name': 'Suhbat', 'verbose_name_plural': 'Suhbatlar'},
        ),
    ]
