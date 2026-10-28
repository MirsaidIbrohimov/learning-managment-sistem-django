from django.core.management.base import BaseCommand, CommandError

from accounts import inpay
from accounts.tezcheck import TezCheckError


class Command(BaseCommand):
    help = ("inPAY kassasining webhook imzo sirini (whsec_…) oladi. Natijani .env faylidagi "
            "INPAY_WEBHOOK_SECRET ga yozing. Faqat sk_live_ kalit bilan va oq röyxatdagi IP'dan işlaydi.")

    def handle(self, *args, **options):
        if not inpay.configured():
            raise CommandError('INPAY_SECRET_KEY sozlanmagan.')
        try:
            secret = inpay.fetch_webhook_secret()
        except TezCheckError as exc:
            raise CommandError(f'{exc} (kod: {getattr(exc, "code", "") or "nomaʼlum"})') from None
        if not str(secret).startswith('whsec_'):
            raise CommandError('inPAY javobida webhook siri topilmadi.')
        self.stdout.write(f'INPAY_WEBHOOK_SECRET={secret}')
