"""
0080 — Adds student_id to CustomUser + PaymeTransaction + ClickTransaction models.
Data migration: backfills unique 5-digit IDs for all existing users.
"""
import random
from django.db import migrations, models
import django.db.models.deletion


def generate_unique_id(existing_ids):
    """Return a random 5-digit int not already in existing_ids."""
    while True:
        sid = random.randint(10000, 99999)
        if sid not in existing_ids:
            existing_ids.add(sid)
            return sid


def backfill_student_ids(apps, schema_editor):
    """Assign a unique student_id to every user that doesn't have one yet."""
    CustomUser = apps.get_model('accounts', 'CustomUser')
    existing = set(
        CustomUser.objects.exclude(student_id__isnull=True)
        .values_list('student_id', flat=True)
    )
    users_without_id = CustomUser.objects.filter(student_id__isnull=True)
    batch = []
    for user in users_without_id:
        user.student_id = generate_unique_id(existing)
        batch.append(user)
    if batch:
        CustomUser.objects.bulk_update(batch, ['student_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0079_user_is_finished_profession_has_certificate'),
    ]

    operations = [
        # 1. Add student_id column (nullable first so existing rows are fine)
        migrations.AddField(
            model_name='customuser',
            name='student_id',
            field=models.IntegerField(
                blank=True,
                db_index=True,
                editable=False,
                null=True,
                unique=True,
                verbose_name="Öquvçi ID raqami",
            ),
        ),

        # 2. Backfill IDs for existing users
        migrations.RunPython(backfill_student_ids, migrations.RunPython.noop),

        # 3. Add PaymeTransaction table
        migrations.CreateModel(
            name='PaymeTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('payme_id', models.CharField(max_length=255, unique=True, verbose_name='Payme tranzaksiya ID')),
                ('amount', models.DecimalField(decimal_places=0, max_digits=14, verbose_name='Summa (tiyin)')),
                ('state', models.IntegerField(
                    choices=[(1, "Yaratilgan"), (2, "Tölangan"), (-1, "Bekor qilingan"), (-2, "Qaytarilgan")],
                    default=1,
                    verbose_name='Holat',
                )),
                ('time', models.BigIntegerField(verbose_name='Yaratiliş vaqti (ms)')),
                ('create_time', models.BigIntegerField(blank=True, null=True, verbose_name='Server create vaqti (ms)')),
                ('perform_time', models.BigIntegerField(blank=True, null=True, verbose_name='Perform vaqti (ms)')),
                ('cancel_time', models.BigIntegerField(blank=True, null=True, verbose_name='Bekor etiş vaqti (ms)')),
                ('reason', models.IntegerField(blank=True, null=True, verbose_name='Bekor etiş sababi')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('student', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='payme_transactions',
                    to='accounts.customuser',
                    verbose_name="Öquvçi",
                )),
            ],
            options={
                'verbose_name': 'Payme tranzaksiyasi',
                'verbose_name_plural': 'Payme tranzaksiyalari',
                'ordering': ['-created_at'],
            },
        ),

        # 4. Add ClickTransaction table
        migrations.CreateModel(
            name='ClickTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('click_trans_id', models.BigIntegerField(unique=True, verbose_name='Click tranzaksiya ID')),
                ('click_paydoc_id', models.BigIntegerField(blank=True, null=True, verbose_name='Click paydoc ID')),
                ('merchant_trans_id', models.CharField(blank=True, max_length=200, verbose_name='Merchant trans ID (student_id)')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=14, verbose_name="Summa (söm)")),
                ('is_confirmed', models.BooleanField(default=False, verbose_name='Tasdiqlangan')),
                ('error', models.IntegerField(default=0, verbose_name='Xato kodi')),
                ('error_note', models.CharField(blank=True, max_length=500, verbose_name='Xato matni')),
                ('sign_time', models.CharField(blank=True, max_length=30, verbose_name='Imzo vaqti')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('student', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='click_transactions',
                    to='accounts.customuser',
                    verbose_name="Öquvçi",
                )),
            ],
            options={
                'verbose_name': 'Click tranzaksiyasi',
                'verbose_name_plural': 'Click tranzaksiyalari',
                'ordering': ['-created_at'],
            },
        ),
    ]
