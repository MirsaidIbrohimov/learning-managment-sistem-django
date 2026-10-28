# Generated manually because the workspace Python virtualenv points to a
# missing interpreter; verify with makemigrations in the deployment environment.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0122_blockedsection_startup_choice'),
    ]

    operations = [
        migrations.CreateModel(
            name='TezCheckPaymentOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('external_reference', models.CharField(max_length=128, unique=True)),
                ('bill_id', models.CharField(blank=True, db_index=True, max_length=100)),
                ('bill_reference', models.CharField(blank=True, max_length=100)),
                ('payment_id', models.CharField(blank=True, db_index=True, max_length=100)),
                ('payment_url', models.URLField(blank=True, max_length=1000)),
                ('amount_minor', models.PositiveBigIntegerField(verbose_name='Summa (tiyin)')),
                ('fee_minor', models.PositiveBigIntegerField(default=0, verbose_name='Komissiya (tiyin)')),
                ('net_minor', models.PositiveBigIntegerField(default=0, verbose_name='Sof tuşum (tiyin)')),
                ('currency', models.CharField(default='UZS', max_length=3)),
                ('provider_code', models.CharField(blank=True, max_length=40)),
                ('environment', models.CharField(blank=True, max_length=20)),
                ('status', models.CharField(choices=[('pending', 'Kutilmoqda'), ('paid', "Tölangan"), ('failed', 'Amalga oşmadi'), ('expired', "Muddati ötgan"), ('cancelled', 'Bekor qilingan'), ('refunded', 'Qaytarilgan'), ('review', 'Tekşiruv kerak')], db_index=True, default='pending', max_length=16)),
                ('billing_month', models.PositiveSmallIntegerField()),
                ('billing_year', models.PositiveSmallIntegerField()),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('available_until', models.DateTimeField(blank=True, null=True)),
                ('last_error', models.CharField(blank=True, max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='tezcheck_payment_orders', to=settings.AUTH_USER_MODEL, verbose_name="Öquvçi")),
            ],
            options={
                'verbose_name': 'Tezcheck tölov buyurtmasi',
                'verbose_name_plural': 'Tezcheck tölov buyurtmalari',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='TezCheckWebhookEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_id', models.CharField(max_length=100, unique=True)),
                ('event_type', models.CharField(blank=True, max_length=80)),
                ('delivery_id', models.CharField(blank=True, max_length=100)),
                ('payload', models.JSONField(default=dict)),
                ('signature_valid', models.BooleanField(default=False)),
                ('processed', models.BooleanField(db_index=True, default=False)),
                ('processing_error', models.CharField(blank=True, max_length=500)),
                ('received_at', models.DateTimeField(auto_now_add=True)),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
                ('order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='webhook_events', to='accounts.tezcheckpaymentorder')),
            ],
            options={
                'verbose_name': 'Tezcheck webhook hodisasi',
                'verbose_name_plural': 'Tezcheck webhook hodisalari',
                'ordering': ['-received_at'],
            },
        ),
    ]
