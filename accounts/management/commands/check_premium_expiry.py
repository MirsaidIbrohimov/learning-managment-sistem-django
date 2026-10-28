from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from accounts.models import CustomUser, Message


class Command(BaseCommand):
    help = 'Premium muddati tugayotgan va tugagan foydalanuvçilarni tekşiriş'

    def handle(self, *args, **kwargs):
        now = timezone.now()

        expiring = CustomUser.objects.filter(
            is_premium=True,
            premium_expires_at__lte=now + timedelta(days=2),
            premium_expires_at__gt=now
        )

        for user in expiring:
            days_left = (user.premium_expires_at - now).days
            already_notified = Message.objects.filter(
                recipient=user,
                title="Premium muddati tugamoqda ⚠️",
                created_at__gte=now - timedelta(days=1)
            ).exists()

            if not already_notified:
                Message.objects.create(
                    recipient=user,
                    title="Premium muddati tugamoqda ⚠️",
                    content=f"Sizning Premium obunangiz muddati {days_left} kundan söng tugaydi ({user.premium_expires_at.strftime('%d.%m.%Y %H:%M')}).\n\nIltimos, muddatni uzaytiring! Market bölimidan Premium uzaytiriş tugmasini bosing.",
                    message_type='reminder'
                )
                self.stdout.write(f"Eslatma yuborildi: {user.full_name} ({days_left} kun qoldi)")

        expired = CustomUser.objects.filter(
            is_premium=True,
            premium_expires_at__lte=now
        )

        for user in expired:
            user.is_premium = False
            user.save(update_fields=['is_premium'])

            Message.objects.create(
                recipient=user,
                title="Premium muddati tugadi",
                content="Sizning Premium obunangiz muddati tugadi.\n\nQayta oliş uçun Market bölimiga kiring.",
                message_type='system'
            )
            self.stdout.write(f"Premium olib taşlandi: {user.full_name}")

        self.stdout.write(self.style.SUCCESS('Premium tekşiruvi yakunlandi!'))
