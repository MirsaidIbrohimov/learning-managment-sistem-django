from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_yordamchi', '0005_chat_folders_pin_rating'),
    ]

    operations = [
        migrations.CreateModel(
            name='KnowledgeChunk',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('profession_id', models.IntegerField(blank=True, db_index=True, null=True)),
                ('source_type', models.CharField(default='lesson', max_length=30)),
                ('source_id', models.IntegerField(blank=True, null=True)),
                ('title', models.CharField(blank=True, default='', max_length=300)),
                ('content', models.TextField()),
                ('embedding', models.TextField(blank=True, default='')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Bilim bölagi',
                'verbose_name_plural': 'Bilim bazasi',
            },
        ),
    ]
