from django.db import migrations, models


class Migration(migrations.Migration):
    """
    0093 migration ustunni DB dan öçirdi, lekin state bilan nomuvofiqlik qoldi.
    Bu migration state'ni DB bilan moslaştiradi — DB'ga tegmaydi.
    """

    dependencies = [
        ('accounts', '0095_update_final_test_payment_amount'),
    ]

    operations = [
        # Avval state'ga qöşamiz (0093 uni state'dan olgan edi)
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
        # Keyin state'dan öçiramiz (DB'da ustun yöq — tegmaymiz)
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
