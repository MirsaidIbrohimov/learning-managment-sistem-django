# Serverdagi migratsiya tarixini tuzatish: coin.0007 qo'llangan, lekin coin.0006 yozilmagan.
#   python manage.py shell -c "exec(open('scripts/fix_coin_0006.py', encoding='utf-8').read())"
# 0006 faqat 4 ta indeks qo'shadi: bazada yo'q bo'lganlari yaratiladi, keyin 0006
# "qo'llangan" deb yoziladi. Ma'lumotlarga tegilmaydi.
from django.db import connection, models
from django.db.migrations.recorder import MigrationRecorder
from coin.models import ActivityLog, CoinTransaction

INDEXES = [
    (ActivityLog, models.Index(fields=['user', '-created_at'], name='coin_activi_user_id_230bbb_idx')),
    (ActivityLog, models.Index(fields=['user', 'action_type'], name='coin_activi_user_id_dc16ce_idx')),
    (CoinTransaction, models.Index(fields=['user', '-created_at'], name='coin_cointr_user_id_b2b86f_idx')),
    (CoinTransaction, models.Index(fields=['user', 'action'], name='coin_cointr_user_id_39ae21_idx')),
]

recorder = MigrationRecorder(connection)
if recorder.migration_qs.filter(app='coin', name='0006_add_performance_indexes').exists():
    print("coin.0006 allaqachon yozilgan — hech narsa qilinmadi.")
else:
    with connection.schema_editor() as editor:
        for model, index in INDEXES:
            with connection.cursor() as cursor:
                existing = connection.introspection.get_constraints(cursor, model._meta.db_table)
            if index.name in existing:
                print("bor:", index.name)
            else:
                editor.add_index(model, index)
                print("yaratildi:", index.name)
    recorder.record_applied('coin', '0006_add_performance_indexes')
    print("coin.0006 qo'llangan deb yozildi.")
