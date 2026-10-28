"""One-time cleanup: sever contract students from monthly payments.

Students already switched to contract mode (``StudentBalance.is_contract=True``)
before this fix may still have leftover unpaid ``PaymentRecord`` rows created
while they were on the regular monthly plan. Those rows keep surfacing as
"Tölanmagan" in reminders/exports/counts even though the payments page hides
the students themselves. Delete only the *unpaid* rows for contract students;
real (paid) payment history is preserved.
"""
from django.db import migrations


def clean_contract_unpaid(apps, schema_editor):
    PaymentRecord = apps.get_model('accounts', 'PaymentRecord')
    StudentBalance = apps.get_model('accounts', 'StudentBalance')

    contract_user_ids = StudentBalance.objects.filter(
        is_contract=True
    ).values_list('user_id', flat=True)

    PaymentRecord.objects.filter(
        user_id__in=list(contract_user_ids), is_paid=False
    ).delete()


def noop_reverse(apps, schema_editor):
    # Deleted placeholder records can't be meaningfully restored; the payments
    # page re-creates them automatically if a student returns to active mode.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0109_homeworksubmission_coins_earned'),
    ]

    operations = [
        migrations.RunPython(clean_contract_unpaid, noop_reverse),
    ]
