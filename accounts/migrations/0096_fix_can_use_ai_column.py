from django.db import migrations, models


class Migration(migrations.Migration):
    """
    0093 migration ustunni DB dan o'chirdi, lekin state bilan nomuvofiqlik qoldi.
    Bu migration state'ni DB bilan moslashtiradi — DB'ga tegmaydi.
    """

    dependencies = [
        ('accounts', '0095_update_final_test_payment_amount'),
    ]

    operations = [
        # Avval state'ga qo'shamiz (0093 uni state'dan olgan edi)
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
        # Keyin state'dan o'chiramiz (DB'da ustun yo'q — tegmaymiz)
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name='customuser',
                    name='can_use_ai',
                ),
            ],
            database_operations=[],
        ),
    ]
