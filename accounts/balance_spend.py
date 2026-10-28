"""Öquvçi pul balansidan (StudentBalance) xarid uçun yeçiş.

Oylik tölovdan ortgan mablağni tanga yoki pulli kurs sotib olişga işlatiş
mumkin. Yeçim bitta şartli SQL UPDATE bilan qilinadi — parallel sörovlar
balansni minusga tuşira olmaydi (SQLite'da ham). Har bir yeçim balans
tarixiga (BalanceTopUp) yoziladi.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import BalanceTopUp, StudentBalance


class BalanceError(Exception):
    """Foydalanuvçiga körsatiladigan xavfsiz xabar."""


def spendable_balance(user):
    """Xarid uçun işlatsa böladigan summa (söm). Şartnoma balansi işlatilmaydi."""
    if not getattr(user, 'is_authenticated', False) or not getattr(user, 'is_learner', False):
        return 0
    bal = StudentBalance.objects.filter(user=user).values('amount', 'is_contract').first()
    if not bal or bal['is_contract']:
        return 0
    return max(0, int(bal['amount'] or 0))


@transaction.atomic
def spend_balance(user, amount, note):
    """Balansdan `amount` söm yeçadi; yetmasa BalanceError. Qolgan balansni qaytaradi."""
    amount = int(amount)
    if amount <= 0:
        raise BalanceError("Summa notöğri.")
    bal = StudentBalance.objects.filter(user=user).first()
    if bal is None or bal.is_contract:
        raise BalanceError("Balansdan xarid qiliş imkoni yöq.")
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
