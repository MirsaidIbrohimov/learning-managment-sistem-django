from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0017_boardmatch_spectator_ids'),
    ]

    operations = [
        migrations.AddField(
            model_name='prompt',
            name='usage',
            field=models.CharField(
                choices=[('practice', 'Mashq'), ('competition', 'Musobaqa'), ('both', 'Ikkalasi')],
                default='both',
                max_length=15,
                verbose_name='Qayerda ishlatiladi',
            ),
        ),
        migrations.AddField(
            model_name='competition',
            name='prompts',
            field=models.ManyToManyField(
                blank=True,
                help_text="Tanlansa, musobaqada faqat shu matnlar chiqadi. Bo'sh qolsa — 'Musobaqa' rejimidagi matnlar ishlatiladi.",
                related_name='competitions',
                to='games.prompt',
                verbose_name='Maxsus topshiriqlar',
            ),
        ),
    ]
