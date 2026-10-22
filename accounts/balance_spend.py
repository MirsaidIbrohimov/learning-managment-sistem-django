"""O'quvchi pul balansidan (StudentBalance) xarid uchun yechish.

Oylik to'lovdan ortgan mablag'ni tanga yoki pulli kurs sotib olishga ishlatish
mumkin. Yechim bitta shartli SQL UPDATE bilan qilinadi — parallel so'rovlar
balansni minusga tushira olmaydi (SQLite'da ham). Har bir yechim balans
tarixiga (BalanceTopUp) yoziladi.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import BalanceTopUp, StudentBalance


class BalanceError(Exception):
    """Foydalanuvchiga ko'rsatiladigan xavfsiz xabar."""


def spendable_balance(user):
    """Xarid uchun ishlatsa bo'ladigan summa (so'm). Shartnoma balansi ishlatilmaydi."""
    if not getattr(user, 'is_authenticated', False) or not getattr(user, 'is_learner', False):
        return 0
    bal = StudentBalance.objects.filter(user=user).values('amount', 'is_contract').first()
    if not bal or bal['is_contract']:
        return 0
    return max(0, int(bal['amount'] or 0))


@transaction.atomic
def spend_balance(user, amount, note):
    """Balansdan `amount` so'm yechadi; yetmasa BalanceError. Qolgan balansni qaytaradi."""
    amount = int(amount)
    if amount <= 0:
        raise BalanceError("Summa noto'g'ri.")
    bal = StudentBalance.objects.filter(user=user).first()
    if bal is None or bal.is_contract:
        raise BalanceError("Balansdan xarid qilish imkoni yo'q.")
    updated = StudentBalance.objects.filter(
        pk=bal.pk, is_contract=False, amount__gte=Decimal(amount),
    ).update(amount=F('amount') - Decimal(amount), updated_at=timezone.now())
    if not updated:
        raise BalanceError("Balansingizda mablag' yetarli emas.")
    BalanceTopUp.objects.create(
        student=user, amount=Decimal(amount), operation='deduct', added_by=user, note=note[:500],
    )
    bal.refresh_from_db(fields=['amount'])
    return int(bal.amount)
