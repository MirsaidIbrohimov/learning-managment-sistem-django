from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('accounts', '0130_pending_recovery_password')]
    operations = [migrations.CreateModel(
        name='EmailLoginChallenge',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('token', models.CharField(max_length=64, unique=True)),
            ('email', models.EmailField(max_length=254)),
            ('code_hash', models.CharField(max_length=128)),
            ('expires_at', models.DateTimeField()),
            ('attempts', models.PositiveSmallIntegerField(default=0)),
            ('used', models.BooleanField(default=False)),
            ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ],
    )]
