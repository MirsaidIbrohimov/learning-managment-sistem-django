"""Bazadagi matnlarni yangi özbek alifbosiga ötkazadi (O' → Ö, G' → Ğ, Ş → Ş, Ç → Ç).

    python manage.py convert_alphabet                 # faqat hisobot (heç narsa yozilmaydi)
    python manage.py convert_alphabet --apply         # bazani yangilaydi
    python manage.py convert_alphabet --include-names # ism-familiyalarni ham ögiradi
    python manage.py convert_alphabet --only courses.Lesson accounts.Profession

Kurs, dars, test, blog, bildirişnoma va boşqa matnli maydonlar (CharField,
TextField, JSONField içidagi satrlar) ögiriladi. Login, email, parol, token,
URL, slug, fayl yöli, kod va IP kabi texnik maydonlar tegilmaydi. Choices
maydonlarida faqat yangi qiymat ham ruxsat etilgan variant bölsa özgartiriladi.
"""
from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import models, transaction

from accounts.alphabet import to_new_alphabet_value

SKIP_APPS = {"admin", "auth", "contenttypes", "sessions", "authtoken", "token_blacklist", "django_celery_beat"}
SKIP_FIELD_TYPES = (
    models.EmailField, models.URLField, models.SlugField, models.UUIDField,
    models.GenericIPAddressField, models.FilePathField,
)
# Nomida şu bölak bölsa — texnik maydon.
SKIP_NAME_PARTS = (
    "password", "token", "secret", "hash", "key", "slug", "url", "link", "email",
    "username", "login", "phone", "ip_", "_ip", "user_agent", "session", "path",
    "file", "code", "source", "signature", "nonce", "otp", "mime", "content_type",
    "extension", "color", "colour", "icon", "css", "js_", "html_id", "external_id",
    "provider", "gateway", "payload", "headers", "telegram_id", "chat_id", "card",
    "pinfl", "passport", "jshshir", "inn", "language", "lang", "timezone", "domain",
    "telegram_name", "typed_text",
)
NAME_FIELDS = (
    "first_name", "last_name", "middle_name", "full_name", "father_name", "mother_name",
    "fio", "student_name", "teacher_name", "parent_name", "author",
)


def _convert_json(value):
    if isinstance(value, str):
        return to_new_alphabet_value(value)
    if isinstance(value, list):
        return [_convert_json(v) for v in value]
    if isinstance(value, dict):
        return {k: _convert_json(v) for k, v in value.items()}
    return value


def _is_name_field(name):
    return name in NAME_FIELDS or name.endswith("_name") and any(p in name for p in ("first", "last", "full", "father", "mother"))


def _text_fields(model, include_names):
    for field in model._meta.concrete_fields:
        if not isinstance(field, (models.CharField, models.TextField, models.JSONField)):
            continue
        if isinstance(field, SKIP_FIELD_TYPES) or field.primary_key:
            continue
        name = field.name.lower()
        if _is_name_field(name):
            if include_names:
                yield field
            continue
        if any(part in name for part in SKIP_NAME_PARTS):
            continue
        yield field


class Command(BaseCommand):
    help = "Bazadagi matnlarni yangi özbek alifbosiga (Ö Ğ Ş Ç) ötkazadi."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Özgarişlarni bazaga yoziş.")
        parser.add_argument("--include-names", action="store_true", help="Ism-familiya maydonlarini ham ögiriş.")
        parser.add_argument("--only", nargs="*", default=None, metavar="app.Model", help="Faqat şu modellar.")
        parser.add_argument("--samples", type=int, default=0, help="Har maydon uçun neçta misol körsatiş.")

    def handle(self, *args, apply=False, include_names=False, only=None, samples=0, **opts):
        only = {o.lower() for o in only} if only else None
        total_rows = total_fields = 0
        for model in apps.get_models():
            meta = model._meta
            if meta.proxy or not meta.managed or meta.app_label in SKIP_APPS:
                continue
            if only and meta.label_lower not in only:
                continue
            fields = list(_text_fields(model, include_names))
            if not fields:
                continue
            changed_rows, per_field = 0, {}
            names = [f.attname for f in fields]
            qs = model._default_manager.all().only(meta.pk.attname, *names)
            with transaction.atomic():
                for obj in qs.iterator(chunk_size=500):
                    updates = []
                    for field in fields:
                        old = getattr(obj, field.attname)
                        if old is None or old == "":
                            continue
                        if isinstance(field, models.JSONField):
                            new = _convert_json(old)
                        elif isinstance(old, str):
                            new = to_new_alphabet_value(old)
                        else:
                            continue
                        if new == old:
                            continue
                        if field.choices and new not in {str(k) for k, _ in field.flatchoices}:
                            continue
                        stat = per_field.setdefault(field.name, [0, []])
                        stat[0] += 1
                        if len(stat[1]) < samples:
                            stat[1].append((str(old)[:80], str(new)[:80]))
                        setattr(obj, field.attname, new)
                        updates.append(field.attname)
                    if updates:
                        changed_rows += 1
                        if apply:
                            model._default_manager.filter(pk=obj.pk).update(
                                **{a: getattr(obj, a) for a in updates}
                            )
            if changed_rows:
                total_rows += changed_rows
                total_fields += sum(v[0] for v in per_field.values())
                detail = ", ".join(f"{k}={v[0]}" for k, v in per_field.items())
                self.stdout.write(f"{meta.label}: {changed_rows} qator ({detail})")
                for k, v in per_field.items():
                    for o, n in v[1]:
                        self.stdout.write(f"    {k}: {o!r} -> {n!r}")
        verb = "yangilandi" if apply else "yangilanadi (--apply bilan)"
        self.stdout.write(self.style.SUCCESS(f"Jami: {total_rows} qator, {total_fields} maydon {verb}."))
