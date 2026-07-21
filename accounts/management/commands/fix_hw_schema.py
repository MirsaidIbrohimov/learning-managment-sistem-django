"""
Uy vazifa jadvallarining sxemasini modelga moslashtiradi.

Migratsiya to'liq qo'llanmagan serverlarda `accounts_homeworksubmission`,
`accounts_homeworkrevision` yoki `accounts_homeworkmessage` jadvallarida
modelда bor, lekin bazada yo'q ustunlar (masalan `coins_earned`) bo'lishi mumkin.
Bu holda vazifa topshirish/qayta topshirish 500 (JSON o'rniga HTML) beradi.

Bu buyruq FAQAT yetishmayotgan ustunlarni qo'shadi (Django schema_editor orqali),
hech qanday ustun yoki ma'lumotni o'chirmaydi. Xavfsiz va qayta ishga tushirsa bo'ladi.

Ishlatish:
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
    help = "Uy vazifa jadvallariga yetishmayotgan ustunlarni xavfsiz qo'shadi."

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
            self.stdout.write(self.style.SUCCESS("Qo'shilgan ustunlar: " + ", ".join(added)))
        else:
            self.stdout.write("Qo'shilgan ustun yo'q — hammasi joyida edi.")

        if failed:
            self.stdout.write(self.style.ERROR("Qo'shib bo'lmadi: " + "; ".join(failed)))

        self._verify()
        self._show_migrations()

    def _verify(self):
        """Xavfli maydonlarni o'qib, ustunlar haqiqatan mavjudligini tekshiramiz."""
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
            self.stdout.write(self.style.SUCCESS("Tekshiruv: HomeworkSubmission/Revision o'qish OK"))
        except Exception:
            self.stdout.write(self.style.ERROR("Tekshiruvda XATO (ustun hali ham yetishmayapti?):"))
            self.stdout.write(traceback.format_exc())

    def _show_migrations(self):
        try:
            from django.db.migrations.recorder import MigrationRecorder
            names = list(
                MigrationRecorder(connection).migration_qs
                .filter(app="accounts").order_by("id")
                .values_list("name", flat=True)
            )[-6:]
            self.stdout.write("Oxirgi qo'llangan migratsiyalar: " + ", ".join(names))
        except Exception:
            pass
