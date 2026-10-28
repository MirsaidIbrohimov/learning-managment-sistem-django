from django.core.management.base import BaseCommand, CommandError

from accounts import curiosity


class Command(BaseCommand):
    help = "Boş sahifadagi \"Bilasizmi?\" savollarini OpenAI orqali yaratadi (OPENAI_API_KEY kerak)."

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=curiosity.BATCH_SIZE)

    def handle(self, *args, count, **options):
        if not 1 <= count <= 50:
            raise CommandError('--count 1 dan 50 gaça bölişi kerak.')
        if curiosity._client() is None:
            raise CommandError('OPENAI_API_KEY sozlanmagan yoki openai paketi örnatilmagan.')
        try:
            created = curiosity.generate_batch(count)
        except Exception as exc:
            raise CommandError(f'OpenAI javobi olinmadi: {type(exc).__name__}') from None
        self.stdout.write(self.style.SUCCESS(f'{created} ta yangi savol saqlandi.'))
