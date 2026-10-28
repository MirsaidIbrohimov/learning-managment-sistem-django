from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0112_repair_homework_schema_drift'),
    ]

    operations = [
        migrations.AddField(
            model_name='balancetopup',
            name='operation',
            field=models.CharField(
                choices=[('add', "Qöşiş"), ('deduct', 'Ayiriş')],
                default='add',
                max_length=10,
                verbose_name='Amal',
            ),
        ),
        migrations.AlterModelOptions(
            name='balancetopup',
            options={
                'ordering': ['-created_at'],
                'verbose_name': "Balans özgarişi",
                'verbose_name_plural': "Balans özgarişlari tarixi",
            },
        ),
    ]
