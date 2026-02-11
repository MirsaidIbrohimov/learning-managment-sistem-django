from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0034_add_text_submission'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='premium_expires_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Premium tugash sanasi'),
        ),
        migrations.CreateModel(
            name='PremiumRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('plan', models.CharField(choices=[('weekly', 'Haftalik (350 coin)'), ('monthly', '1 oylik (700 coin)'), ('bimonthly', '2 oylik (1000 coin)')], max_length=20, verbose_name='Tarif reja')),
                ('status', models.CharField(choices=[('pending', 'Kutilmoqda'), ('approved', 'Tasdiqlangan'), ('rejected', 'Rad etilgan')], default='pending', max_length=20, verbose_name='Holat')),
                ('is_extension', models.BooleanField(default=False, verbose_name='Muddatni uzaytirish')),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviewed_premium_requests', to=settings.AUTH_USER_MODEL)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='premium_requests', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': "Premium so'rovi",
                'verbose_name_plural': "Premium so'rovlari",
                'ordering': ['-created_at'],
            },
        ),
    ]
