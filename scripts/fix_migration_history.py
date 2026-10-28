# Migratsiya tarixidagi "tushib qolgan" yozuvlarni tuzatadi
# (InconsistentMigrationHistory: X is applied before its dependency Y).
#
#   Faqat hisobot:  python manage.py shell -c "exec(open('scripts/fix_migration_history.py', encoding='utf-8').read())"
#   Tuzatish:       APPLY=1 python manage.py shell -c "exec(open('scripts/fix_migration_history.py', encoding='utf-8').read())"
#
# Qo'llangan migratsiyalarning yozilmagan barcha bog'liqliklari topiladi. Har biri uchun
# bazadagi holat tekshiriladi:
#   * jadval/ustun/indeks allaqachon bor  -> faqat "qo'llangan" deb yoziladi (fake);
#   * hali yo'q                           -> migratsiya haqiqatan bajariladi;
#   * qisman bor                          -> tegilmaydi, hisobotda ko'rsatiladi.
import os

from django.db import connection
from django.db.migrations import operations as ops
from django.db.migrations.executor import MigrationExecutor

APPLY = os.environ.get("APPLY") == "1"

executor = MigrationExecutor(connection)
loader = executor.loader
graph = loader.graph
applied = set(loader.applied_migrations)

# Qo'llangan migratsiyalarning yozilmagan ajdodlari
missing = set()
for key in applied:
    if key not in graph.nodes:
        continue
    for anc in graph.forwards_plan(key):
        if anc not in applied and anc[0] in loader.migrated_apps:
            missing.add(anc)

plan = [m for m, _ in executor.migration_plan(graph.leaf_nodes(), clean_start=True)]
# Bog'liqliklardan tashqari: yozilmagan, lekin jadvali allaqachon bor migratsiyalar ham
# ("table already exists" xatosi) shu yerda tekshiriladi.
ordered = [m for m in plan if (m.app_label, m.name) not in applied]


def _tables():
    with connection.cursor() as c:
        return set(connection.introspection.table_names(c))


def _columns(table):
    with connection.cursor() as c:
        return {col.name for col in connection.introspection.get_table_description(c, table)}


def _constraints(table):
    with connection.cursor() as c:
        return set(connection.introspection.get_constraints(c, table))


def check(migration):
    """Har bir tekshiriladigan amal uchun True (bazada bor) / False (yo'q)."""
    state = loader.project_state((migration.app_label, migration.name), at_end=True)
    results = []
    tables = _tables()

    def table_of(model_name):
        return state.apps.get_model(migration.app_label, model_name)._meta.db_table

    for op in migration.operations:
        try:
            if isinstance(op, ops.CreateModel):
                results.append((f"jadval {op.name}", table_of(op.name) in tables))
            elif isinstance(op, ops.DeleteModel):
                prev = loader.project_state((migration.app_label, migration.name), at_end=False)
                t = prev.apps.get_model(migration.app_label, op.name)._meta.db_table
                results.append((f"jadval o'chirilgan {op.name}", t not in tables))
            elif isinstance(op, ops.RemoveField):
                prev = loader.project_state((migration.app_label, migration.name), at_end=False)
                model = prev.apps.get_model(migration.app_label, op.model_name)
                t = model._meta.db_table
                col = model._meta.get_field(op.name).column
                results.append((f"ustun o'chirilgan {op.model_name}.{op.name}",
                                t in tables and col not in _columns(t)))
            elif isinstance(op, ops.AddField):
                model = state.apps.get_model(migration.app_label, op.model_name)
                field = model._meta.get_field(op.name)
                if field.many_to_many:
                    results.append((f"m2m {op.model_name}.{op.name}",
                                    field.remote_field.through._meta.db_table in tables))
                else:
                    t = model._meta.db_table
                    results.append((f"ustun {op.model_name}.{op.name}",
                                    t in tables and field.column in _columns(t)))
            elif isinstance(op, ops.AddIndex):
                t = table_of(op.model_name)
                results.append((f"indeks {op.index.name}", t in tables and op.index.name in _constraints(t)))
            elif isinstance(op, ops.AddConstraint):
                t = table_of(op.model_name)
                results.append((f"cheklov {op.constraint.name}",
                                t in tables and op.constraint.name in _constraints(t)))
        except LookupError:
            pass
    return results


if not ordered:
    print("Tarix toza — yozilmagan migratsiya yo'q.")

for migration in ordered:
    key = (migration.app_label, migration.name)
    results = check(migration)
    present = [n for n, ok in results if ok]
    absent = [n for n, ok in results if not ok]
    if not results and key not in missing:
        verdict = "BAJARISH (yangi migratsiya)"
    elif not absent:
        verdict = "FAKE (bazada bor)" if results else "FAKE (tekshiriladigan sxema amali yo'q)"
    elif not present:
        verdict = "BAJARISH (bazada yo'q)"
    else:
        verdict = "QISMAN — qo'lda ko'rish kerak"
    print(f"{key[0]}.{key[1]}: {verdict}")
    for n in absent:
        print(f"    yo'q: {n}")

    if not APPLY or verdict.startswith("QISMAN"):
        continue
    if absent or verdict.startswith("BAJARISH"):
        state = loader.project_state(key, at_end=False)
        executor.apply_migration(state, migration)
        print("    -> bajarildi")
    else:
        executor.recorder.record_applied(*key)
        print("    -> qo'llangan deb yozildi")

if ordered and not APPLY:
    print("\nHech narsa o'zgartirilmadi. Tuzatish uchun APPLY=1 bilan qayta ishga tushiring.")
