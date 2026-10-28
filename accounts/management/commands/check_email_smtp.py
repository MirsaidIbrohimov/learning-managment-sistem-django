"""Check outgoing SMTP connectivity and authentication without sending mail."""
import smtplib

from django.conf import settings
from django.core.mail import get_connection
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Check SMTP connection and authentication without sending a message or printing credentials.'

    def handle(self, *args, **options):
        if settings.EMAIL_BACKEND != 'django.core.mail.backends.smtp.EmailBackend':
            raise CommandError('Email backend SMTP emas. EMAIL_BACKEND sozlamasini tekşiring.')
        if not settings.EMAIL_HOST or not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
            raise CommandError('EMAIL_HOST, EMAIL_HOST_USER yoki EMAIL_HOST_PASSWORD töldirilmagan.')
        if '@' in settings.EMAIL_HOST or '://' in settings.EMAIL_HOST:
            raise CommandError('EMAIL_HOST email yoki URL bölmasligi kerak. Gmail uçun EMAIL_HOST=smtp.gmail.com yozing. Email manzili EMAIL_HOST_USER qatoriga yoziladi.')
        connection = get_connection()
        try:
            connection.open()
        except smtplib.SMTPAuthenticationError:
            raise CommandError('SMTP login rad etildi. Gmail işlatilsa, 2-Step Verification va Google App passwordni tekşiring.') from None
        except smtplib.SMTPException as exc:
            raise CommandError('SMTP server xatosi: ' + type(exc).__name__) from None
        except (OSError, ValueError) as exc:
            raise CommandError('SMTP ulaniş xatosi: ' + type(exc).__name__ + '. Server, port va TLS/SSL sozlamalarini tekşiring.') from None
        else:
            self.stdout.write(self.style.SUCCESS('SMTP ulanişi va autentifikatsiya muvaffaqiyatli. Heç qanday xat yuborilmadi.'))
        finally:
            try:
                connection.close()
            except (OSError, smtplib.SMTPException):
                pass
