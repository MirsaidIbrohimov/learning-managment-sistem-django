from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0085_studentbalance_contract_next_payment'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SecurityEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_type', models.CharField(
                    choices=[
                        ('rate_limit_hit', "Rate limit oşirildi"),
                        ('ip_blocked', 'IP bloklandi'),
                        ('blocked_ip_request', "Bloklangan IP sörov yubordi"),
                        ('sqli_attempt', 'SQL Injection uriniş'),
                        ('xss_attempt', 'XSS uriniş'),
                        ('path_trav', 'Path Traversal uriniş'),
                        ('ssti', 'Template Injection uriniş'),
                        ('cmd_inject', 'Command Injection uriniş'),
                        ('brute_force', 'Brute-force uriniş'),
                        ('failed_login', 'Muvaffaqiyatsiz login'),
                        ('suspicious_upload', 'Şubhali fayl yuklanişga uriniş'),
                        ('csrf_failure', 'CSRF muvaffaqiyatsiz'),
                        ('permission_denied', 'Ruxsatsiz kiriş urinişi'),
                        ('account_locked', 'Hisob bloklandi'),
                        ('password_changed', "Parol özgartirildi"),
                        ('profile_updated', 'Profil yangilandi'),
                        ('admin_action', 'Admin harakat'),
                        ('other', 'Boşqa'),
                    ],
                    db_index=True,
                    max_length=40,
                    verbose_name='Hodisa turi',
                )),
                ('severity', models.CharField(
                    choices=[
                        ('low', '🟢 Past'),
                        ('medium', "🟡 Örta"),
                        ('high', '🔴 Yuqori'),
                        ('critical', '🚨 Kritik'),
                    ],
                    db_index=True,
                    default='medium',
                    max_length=10,
                    verbose_name='Xavf darajasi',
                )),
                ('ip_address', models.CharField(blank=True, db_index=True, max_length=45, verbose_name='IP manzil')),
                ('detail', models.TextField(blank=True, verbose_name='Tafsilot')),
                ('path', models.CharField(blank=True, max_length=500, verbose_name="Sörov yöli")),
                ('user_agent', models.CharField(blank=True, max_length=512, verbose_name='User Agent')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Vaqt')),
                ('resolved', models.BooleanField(default=False, verbose_name='Hal qilindi')),
                ('resolved_at', models.DateTimeField(blank=True, null=True, verbose_name='Hal qilingan vaqt')),
                ('user', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='security_events',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Foydalanuvçi',
                )),
                ('resolved_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='resolved_security_events',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Hal qilgan admin',
                )),
            ],
            options={
                'verbose_name': 'Xavfsizlik hodisasi',
                'verbose_name_plural': 'Xavfsizlik hodisalari',
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['event_type', 'created_at'], name='sec_type_ts_idx'),
                    models.Index(fields=['ip_address', 'created_at'],  name='sec_ip_ts_idx'),
                    models.Index(fields=['severity', 'resolved'],       name='sec_sev_res_idx'),
                ],
            },
        ),
    ]
