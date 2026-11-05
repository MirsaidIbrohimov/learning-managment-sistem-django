"""Musobaqa sovrin fondi: bron qiliş, tölaş va qaytariş.

Ikki xil manba bor:
  * 'system'  — admin musobaqasi: sovrin tizim tomonidan beriladi (coin yaratiladi).
  * 'teacher' — ustoz musobaqasi: sovrin ustozning öz coinlaridan tölanadi.

Ustoz musobaqasida coin heç qaçon "yöqdan" paydo bölmaydi:
  1) yaratişda butun fond (1+2+3-örin) ustoz hisobidan yeçib olinadi va
     `Competition.prize_reserved` da uşlab turiladi;
  2) musobaqa tugaganda ğoliblarga şu fonddan tölanadi;
  3) tölanmay qolgan qism (iştirokçi yetmagan, örin böş) ustozga qaytadi;
  4) musobaqa öçirilsa — bron töliq qaytariladi.

Barça özgarişlar şartli UPDATE bilan bajariladi (compare-and-swap), şuning
uçun parallel sörovlar bir xil coinni ikki marta sarflay/qaytara olmaydi.
"""
from django.db import transaction
from django.db.models import F
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import Competition

PLACE_NAMES = ("1-örin 🥇", "2-örin 🥈", "3-örin 🥉")


class EscrowError(Exception):
    """Foydalanuvçiga körsatiladigan xato (masalan, balans yetarli emas)."""


def _prizes(competition):
    return (competition.coin_1st, competition.coin_2nd, competition.coin_3rd)


@transaction.atomic
def reserve(competition, funder, amount):
    """Yangi ustoz musobaqasi uçun fondni ustoz hisobidan bron qiliş."""
    if amount <= 0:
        return
    if not funder.try_spend_coins(amount, f"Musobaqa sovrin fondi (bron): {competition.title}"):
        raise EscrowError(
            f"Balansingiz yetarli emas: sovrin fondi {amount} coin, "
            f"hisobingizda {funder.coins} coin."
        )
    updated = Competition.objects.filter(pk=competition.pk).update(
        prize_reserved=F('prize_reserved') + amount
    )
    if not updated:
        raise EscrowError("Musobaqa topilmadi.")
    competition.prize_reserved += amount


@transaction.atomic
def adjust(competition, funder, new_total):
    """Sovrinlar özgarganda bronni yangi fondga moslaş.

    Oşsa — farq ustozdan qöşimça yeçiladi; kamaysa — farq qaytariladi.
    """
    current = competition.prize_reserved
    delta = new_total - current
    if delta == 0:
        return
    if delta > 0:
        if not funder.try_spend_coins(delta, f"Musobaqa sovrin fondi (qöşimça bron): {competition.title}"):
            raise EscrowError(
                f"Balansingiz yetarli emas: qöşimça {delta} coin kerak, "
                f"hisobingizda {funder.coins} coin."
            )
    updated = Competition.objects.filter(
        pk=competition.pk, prize_reserved=current, coins_awarded=False,
    ).update(prize_reserved=new_total)
    if not updated:
        # Bron şu orada özgargan (parallel sörov yoki hisob-kitob) — tranzaksiya
        # bekor böladi va yeçilgan coin ham qaytadi.
        raise EscrowError("Sovrin fondi şu orada özgardi. Sahifani yangilab, qayta urinib köring.")
    if delta < 0:
        funder.add_coins(-delta, f"Musobaqa sovrin fondi kamaytirildi: {competition.title}")
    competition.prize_reserved = new_total


@transaction.atomic
def refund(competition, reason=None):
    """Bron qilingan fondni töliq ustozga qaytariş. Qaytarilgan miqdorni beradi."""
    amount = Competition.objects.filter(pk=competition.pk).values_list('prize_reserved', flat=True).first() or 0
    if amount <= 0:
        return 0
    claimed = Competition.objects.filter(pk=competition.pk, prize_reserved=amount).update(prize_reserved=0)
    if not claimed:
        return 0
    competition.prize_reserved = 0
    if competition.created_by_id:
        competition.created_by.add_coins(
            amount, reason or f"Musobaqa sovrin fondi qaytarildi: {competition.title}"
        )
    return amount


@transaction.atomic
def take_from_reserve(competition, amount):
    """Ustoz fondidan bitta tölov uçun coin oliş (Jumanji har sessiyada tölaydi).

    Fonddagidan ortiq bera olmaydi: qaytaradi — haqiqatan ajratilgan miqdor (0 bölişi mumkin).
    """
    if amount <= 0:
        return 0
    budget = (Competition.objects.select_for_update()
              .filter(pk=competition.pk).values_list('prize_reserved', flat=True).first() or 0)
    take = min(amount, budget)
    if take > 0:
        Competition.objects.filter(pk=competition.pk).update(prize_reserved=budget - take)
        competition.prize_reserved = budget - take
    return take


def pay_winners(competition, top_attempts):
    """Ğoliblarga tölaş. Çaqiruvçi tranzaksiya içida bölişi şart.

    Qaytaradi: [(attempt, place_index, amount), ...] — faqat haqiqatan tölanganlar.
    """
    teacher_funded = competition.is_teacher_funded
    if teacher_funded:
        budget = (Competition.objects.select_for_update()
                  .filter(pk=competition.pk)
                  .values_list('prize_reserved', flat=True).first() or 0)
    paid = []
    for idx, attempt in enumerate(top_attempts):
        amount = _prizes(competition)[idx]
        if teacher_funded:
            amount = min(amount, budget)
        user = attempt.user
        # Kursni tugatgan öquvçiga coin qöşilmaydi (add_coins jim ötkazib
        # yuboradi) — bunday örin tölanmagan hisoblanadi va fondda qoladi.
        if amount <= 0 or user.is_finished:
            continue
        user.add_coins(amount, f"Musobaqa ğolibi: {competition.title} ({PLACE_NAMES[idx]})")
        paid.append((attempt, idx, amount))
        if teacher_funded:
            budget -= amount

    if teacher_funded:
        Competition.objects.filter(pk=competition.pk).update(prize_reserved=budget)
        competition.prize_reserved = budget
        if budget > 0:
            refund(competition, f"Musobaqa sovrin fondining işlatilmagan qismi: {competition.title}")
    return paid


def notify_winners(competition, winners):
    """Sayt içidagi xabar + Telegram. Tranzaksiyadan taşqarida çaqiriladi."""
    from accounts.models import Message
    from telegram_bot.utils import notify_user, notify_group

    is_word = competition.game.game_type == 'word_builder'
    lines = []
    for attempt, idx, amount in winners:
        user, place = attempt.user, PLACE_NAMES[idx]
        Message.objects.create(
            title=f"🏆 Tabriklaymiz! {place}",
            content=(
                f"Siz \"{competition.title}\" musobaqasida {place} ni egallaşga muvaffaq böldingiz! "
                f"Sizga {amount} coin mukofot berildi. Zör natija! 🎉"
            ),
            message_type='achievement',
            recipient=user,
        )
        if user.telegram_id:
            notify_user(
                user.telegram_id,
                f"🏆 <b>Tabriklaymiz!</b>\n\n"
                f"Siz <b>\"{competition.title}\"</b> musobaqasida <b>{place}</b> ni egallaşga muvaffaq böldingiz!\n\n"
                f"🪙 Mukofot: <b>+{amount} coin</b>\n\n"
                f"🎉 Zör natija! Davom eting!"
            )
        score = attempt.total_score if is_word else attempt.score
        lines.append(f"{place} — <b>{user.full_name}</b> ({score} ball, +{amount} coin)")

    notify_group(
        f"🏆 <b>Musobaqa natijalari!</b>\n\n"
        f"🎮 <b>{competition.title}</b>\n"
        f"📋 Öyin: {competition.game.title}\n\n"
        + "\n".join(lines) +
        f"\n\n🎉 Ğoliblarni tabriklaymiz!"
    )


@receiver(pre_delete, sender=Competition, dispatch_uid='games_refund_prize_on_delete')
def _refund_on_delete(sender, instance, **kwargs):
    """Qaysi yöl bilan öçirilmasin (admin, ustoz, öyin bilan kaskad) —
    hisob-kitob qilinmagan bron ustozga qaytadi."""
    if instance.prize_reserved and not instance.coins_awarded:
        refund(instance, f"Musobaqa öçirildi, sovrin fondi qaytarildi: {instance.title}")
