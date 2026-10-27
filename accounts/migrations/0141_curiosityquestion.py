from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0140_payment_order_gateway'),
    ]

    operations = [
        migrations.CreateModel(
            name='CuriosityQuestion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.CharField(max_length=255, unique=True, verbose_name='Savol')),
                ('category', models.CharField(max_length=20, verbose_name='Mavzu')),
                ('is_active', models.BooleanField(default=True, verbose_name='Faol')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                'verbose_name': 'Bilasizmi savoli',
                'verbose_name_plural': 'Bilasizmi savollari',
                'ordering': ['-created_at'],
            },
        ),
    ]
