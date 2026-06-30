from django.db import migrations


def drop_can_use_ai_if_exists(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("PRAGMA table_info(accounts_customuser)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'can_use_ai' in columns:
            cursor.execute("ALTER TABLE accounts_customuser DROP COLUMN can_use_ai")


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0095_update_final_test_payment_amount'),
    ]

    operations = [
        migrations.RunPython(drop_can_use_ai_if_exists, migrations.RunPython.noop),
    ]
