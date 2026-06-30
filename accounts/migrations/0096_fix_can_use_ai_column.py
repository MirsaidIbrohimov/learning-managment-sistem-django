from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Migration 0093 da can_use_ai ustuni Django state'dan olib tashlandi,
    lekin SQLite ma'lumotlar bazasida qoldi (NOT NULL, default yo'q).
    Bu migration:
      1. Ustunni Django state'iga qaytaradi (DB'ga tegmaydi — ustun allaqachon bor)
      2. So'ng Django'ning o'zi to'g'ri usulda (table recreation) o'chiradi
    """

    dependencies = [
        ('accounts', '0095_update_final_test_payment_amount'),
    ]

    operations = [
        # 1-qadam: state'ga qaytaramiz, DB'ga tegmaymiz (ustun allaqachon bor)
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='customuser',
                    name='can_use_ai',
                    field=models.BooleanField(default=True),
                ),
            ],
            database_operations=[],
        ),
        # 2-qadam: endi Django to'g'ri usulda o'chiradi (SQLite uchun table recreation)
        migrations.RemoveField(
            model_name='customuser',
            name='can_use_ai',
        ),
    ]
