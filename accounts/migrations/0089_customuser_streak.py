from django.db import migrations, models


def add_streak_columns(apps, schema_editor):
    """streak ustunlarini faqat mavjud bo'lmasa qo'shadi (xavfsiz, takror-bardosh)."""
    conn = schema_editor.connection
    table = 'accounts_customuser'
    with conn.cursor() as cursor:
        existing = [c.name for c in conn.introspection.get_table_description(cursor, table)]
        if 'streak_days' not in existing:
            cursor.execute(f'ALTER TABLE "{table}" ADD COLUMN "streak_days" integer NOT NULL DEFAULT 0')
        if 'last_streak_date' not in existing:
            cursor.execute(f'ALTER TABLE "{table}" ADD COLUMN "last_streak_date" date NULL')


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0089_remove_securityevent_accounts_se_event_t_67c552_idx_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='customuser',
                    name='streak_days',
                    field=models.IntegerField(default=0, verbose_name='Ketma-ket kunlar (streak)'),
                ),
                migrations.AddField(
                    model_name='customuser',
                    name='last_streak_date',
                    field=models.DateField(blank=True, null=True, verbose_name='Oxirgi streak sanasi'),
                ),
            ],
            database_operations=[
                migrations.RunPython(add_streak_columns, noop),
            ],
        ),
    ]
