"""
Uy vazifa jadvallarining sxemasini modelga moslaştiradi.

Migratsiya töliq qöllanmagan serverlarda `accounts_homeworksubmission`,
`accounts_homeworkrevision` yoki `accounts_homeworkmessage` jadvallarida
modelда bor, lekin bazada yöq ustunlar (masalan `coins_earned`) bölişi mumkin.
Bu holda vazifa topshirish/qayta topşiriş 500 (JSON örniga HTML) beradi.

Bu buyruq FAQAT yetişmayotgan ustunlarni qöşadi (Django schema_editor orqali),
heç qanday ustun yoki ma'lumotni öçirmaydi. Xavfsiz va qayta işga tuşirsa böladi.

Işlatiş:
    python manage.py fix_hw_schema
"""
import traceback

from django.core.management.base import BaseCommand
from django.db import connection

from accounts.models import (
    HomeworkSubmission,
    HomeworkRevision,
    HomeworkMessage,
)

TARGET_MODELS = (HomeworkSubmission, HomeworkRevision, HomeworkMessage)


def _existing_columns(table):
    with connection.cursor() as cur:
        return {col.name for col in connection.introspection.get_table_description(cur, table)}


class Command(BaseCommand):
    help = "Uy vazifa jadvallariga yetişmayotgan ustunlarni xavfsiz qöşadi."

    def handle(self, *args, **options):
        added, failed = [], []

        with connection.schema_editor() as schema_editor:
            for model in TARGET_MODELS:
                table = model._meta.db_table
                have = _existing_columns(table)
                for field in model._meta.local_fields:
                    if field.column in have:
                        continue
                    try:
                        schema_editor.add_field(model, field)
                        added.append(f"{table}.{field.column}")
                    except Exception as exc:  # noqa: BLE001 - har bir ustunni alohida himoya qilamiz
                        failed.append(f"{table}.{field.column}: {exc}")

        if added:
            self.stdout.write(self.style.SUCCESS("Qöşilgan ustunlar: " + ", ".join(added)))
        else:
            self.stdout.write("Qöşilgan ustun yöq — hammasi joyida edi.")

        if failed:
            self.stdout.write(self.style.ERROR("Qöşib bölmadi: " + "; ".join(failed)))

        self._verify()
        self._show_migrations()

    def _verify(self):
        """Xavfli maydonlarni öqib, ustunlar haqiqatan mavjudligini tekşiramiz."""
        try:
            sub = HomeworkSubmission.objects.first()
            if sub is not None:
                _ = (
                    sub.coins_earned, sub.coin_awarded, sub.version, sub.revision_count,
                    sub.ai_feedback, sub.ai_checked, sub.is_late, sub.status, sub.grade,
                )
            rev = HomeworkRevision.objects.first()
            if rev is not None:
                _ = (rev.feedback, rev.grade, rev.status, rev.submission_type, rev.text_content, rev.note)
            self.stdout.write(self.style.SUCCESS("Tekşiruv: HomeworkSubmission/Revision öqiş OK"))
        except Exception:
            self.stdout.write(self.style.ERROR("Tekşiruvda XATO (ustun hali ham yetişmayapti?):"))
            self.stdout.write(traceback.format_exc())

    def _show_migrations(self):
        try:
            from django.db.migrations.recorder import MigrationRecorder
            names = list(
                MigrationRecorder(connection).migration_qs
                .filter(app="accounts").order_by("id")
                .values_list("name", flat=True)
            )[-6:]
            self.stdout.write("Oxirgi qöllangan migratsiyalar: " + ", ".join(names))
        except Exception:
            pass
