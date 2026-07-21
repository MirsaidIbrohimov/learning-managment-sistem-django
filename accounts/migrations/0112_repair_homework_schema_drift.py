from django.db import migrations


MODEL_NAMES = (
    'HomeworkSubmission',
    'HomeworkRevision',
    'HomeworkMessage',
)


def repair_homework_schema_drift(apps, schema_editor):
    """Add homework columns missing from partially migrated deployments."""
    connection = schema_editor.connection

    for model_name in MODEL_NAMES:
        model = apps.get_model('accounts', model_name)
        table = model._meta.db_table

        with connection.cursor() as cursor:
            existing_columns = {
                column.name
                for column in connection.introspection.get_table_description(
                    cursor, table
                )
            }

        for field in model._meta.local_fields:
            if field.column not in existing_columns:
                schema_editor.add_field(model, field)
                existing_columns.add(field.column)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0111_unify_homework_submission_versions'),
    ]

    operations = [
        migrations.RunPython(
            repair_homework_schema_drift,
            migrations.RunPython.noop,
        ),
    ]
