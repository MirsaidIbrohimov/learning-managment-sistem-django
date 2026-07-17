from datetime import timedelta

from django.db import migrations


def backfill_ai_coin_history(apps, schema_editor):
    ChatMessage = apps.get_model('ai_yordamchi', 'ChatMessage')
    CoinTransaction = apps.get_model('coin', 'CoinTransaction')

    used_transaction_ids = set()
    paid_messages = ChatMessage.objects.filter(
        role='user',
        coins_spent__gt=0,
    ).select_related('session').order_by('created_at', 'pk')

    for message in paid_messages.iterator():
        matching_transaction = CoinTransaction.objects.filter(
            user_id=message.session.user_id,
            action='remove',
            amount=message.coins_spent,
            reason__icontains='AI yordamchi',
            created_at__gte=message.created_at - timedelta(seconds=5),
            created_at__lte=message.created_at + timedelta(seconds=5),
        ).exclude(pk__in=used_transaction_ids).order_by('created_at').first()

        if matching_transaction:
            used_transaction_ids.add(matching_transaction.pk)
            continue

        transaction = CoinTransaction.objects.create(
            user_id=message.session.user_id,
            amount=message.coins_spent,
            action='remove',
            reason='AI yordamchi bilan suhbat',
        )
        CoinTransaction.objects.filter(pk=transaction.pk).update(
            created_at=message.created_at,
        )
        used_transaction_ids.add(transaction.pk)


class Migration(migrations.Migration):

    dependencies = [
        ('ai_yordamchi', '0006_knowledgechunk'),
        ('coin', '0007_cointransfer'),
    ]

    operations = [
        migrations.RunPython(backfill_ai_coin_history, migrations.RunPython.noop),
    ]
