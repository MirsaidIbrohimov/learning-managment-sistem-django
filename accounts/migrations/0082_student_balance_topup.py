from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def create_balances_for_existing_students(apps, schema_editor):
    """Mavjud o'quvchilar uchun StudentBalance yozuvlari yaratish."""
    CustomUser = apps.get_model('accounts', 'CustomUser')
    StudentBalance = apps.get_model('accounts', 'StudentBalance')
    now = timezone.now()
    student_ids = list(
        CustomUser.objects.filter(role='student').values_list('id', flat=True)
    )
    existing_ids = set(
        StudentBalance.objects.filter(user_id__in=student_ids).values_list('user_id', flat=True)
    )
    to_create = [
        StudentBalance(user_id=uid, amount=0)
        for uid in student_ids if uid not in existing_ids
    ]
    if to_create:
        StudentBalance.objects.bulk_create(to_create, ignore_conflicts=True)


def reverse_balances(apps, schema_editor):
    StudentBalance = apps.get_model('accounts', 'StudentBalance')
    StudentBalance.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0080_add_student_id_payme_click'),
    ]

    operations = [
        # StudentBalance modeli
        migrations.CreateModel(
            name='StudentBalance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=0, default=0, max_digits=14, verbose_name="Balans (so'm)")),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='student_balance',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name="O'quvchi",
                )),
            ],
            options={
                'verbose_name': "O'quvchi balansi",
                'verbose_name_plural': "O'quvchilar balanslari",
            },
        ),
        # BalanceTopUp modeli
        migrations.CreateModel(
            name='BalanceTopUp',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=0, max_digits=14, verbose_name="Miqdor (so'm)")),
                ('note', models.CharField(blank=True, max_length=500, verbose_name='Izoh')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, verbose_name='IP manzil')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('added_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='topups_performed',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Kim tomonidan',
                )),
                ('student', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='balance_topups',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name="O'quvchi",
                )),
            ],
            options={
                'verbose_name': "Balans to'ldirish",
                'verbose_name_plural': "Balans to'ldirish tarixi",
                'ordering': ['-created_at'],
            },
        ),
        # Mavjud o'quvchilar uchun balans yozuvlari
        migrations.RunPython(create_balances_for_existing_students, reverse_balances),
    ]
