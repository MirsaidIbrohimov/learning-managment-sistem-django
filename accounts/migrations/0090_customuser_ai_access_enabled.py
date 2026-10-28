from django.db import migrations, models


def add_ai_access_column(apps, schema_editor):
    """ai_access_enabled ustunini faqat mavjud bölmasa qöşadi (xavfsiz, takror-bardosh)."""
    conn = schema_editor.connection
    table = 'accounts_customuser'
    with conn.cursor() as cursor:
        existing = [c.name for c in conn.introspection.get_table_description(cursor, table)]
        if 'ai_access_enabled' not in existing:
            cursor.execute(
                f'ALTER TABLE "{table}" ADD COLUMN "ai_access_enabled" bool NOT NULL DEFAULT 1'
            )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0089_customuser_streak'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='customuser',
                    name='ai_access_enabled',
                    field=models.BooleanField(
                        default=True,
                        help_text="Öqituvçi uçun AI yordamida test/vazifa yaratiş va baholaş funksiyalariga ruxsat.",
                        verbose_name="AI funksiyasidan foydalaniş ruxsati",
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(add_ai_access_column, noop),
            ],
        ),
    ]
