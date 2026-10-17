from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('accounts', '0131_emailloginchallenge')]
    operations = [
        migrations.AddField(model_name='customuser', name='pending_email', field=models.EmailField(blank=True, max_length=254)),
        migrations.AddField(model_name='customuser', name='email_verification_nonce', field=models.CharField(blank=True, max_length=64)),
        migrations.CreateModel(name='VerifiedEmailBinding', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('email', models.EmailField(max_length=254, unique=True)),
            ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ]),
    ]
