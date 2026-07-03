import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db.migrations.loader import MigrationLoader
from django.db.migrations.state import ProjectState

loader = MigrationLoader(None, ignore_no_migrations=True)
graph = loader.graph

# Full forward plan from empty state (like a fresh/behind server)
targets = graph.leaf_nodes('accounts')
plan = []
seen = set()
for target in targets:
    for migration in graph.forwards_plan(target):
        if migration not in seen:
            plan.append(migration)
            seen.add(migration)

# Only accounts migrations, in planned order
acc_plan = [m for m in plan if m[0] == 'accounts']
print("=== accounts forward order (first 40) ===")
for m in acc_plan[:40]:
    print(m[1])

# Now simulate state build to find failure
state = ProjectState(real_apps=set())
for app, name in plan:
    mig = loader.get_migration(app, name)
    try:
        state = mig.mutate_state(state, preserve=True)
    except Exception as e:
        print(f"\n!!! STATE FAILURE at {app}.{name}: {type(e).__name__}: {e}")
        break
else:
    print("\nNo state failure across full plan.")
