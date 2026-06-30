from django.db import migrations, models


class Migration(migrations.Migration):
    """
    can_use_ai DB ustuni hali mavjud (NOT NULL, default yo'q).
    Bu migration faqat Django state'iga qaytaradi — DB'ga tegmaydi.
    Shu tufayli barcha INSERT lar can_use_ai=True kiritadi va xatolik yo'qoladi.
    """

    dependencies = [
        ('accounts', '0095_update_final_test_payment_amount'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='customuser',
                    name='can_use_ai',
                    field=models.BooleanField(default=True),
                ),
            ],
            database_operations=[],  # DB ustuni allaqachon bor — tegmaymiz
        ),
    ]
