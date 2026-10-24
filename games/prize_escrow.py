"""Musobaqa sovrin fondi: bron qilish, to'lash va qaytarish.

Ikki xil manba bor:
  * 'system'  — admin musobaqasi: sovrin tizim tomonidan beriladi (coin yaratiladi).
  * 'teacher' — ustoz musobaqasi: sovrin ustozning o'z coinlaridan to'lanadi.

Ustoz musobaqasida coin hech qachon "yo'qdan" paydo bo'lmaydi:
  1) yaratishda butun fond (1+2+3-o'rin) ustoz hisobidan yechib olinadi va
     `Competition.prize_reserved` da ushlab turiladi;
  2) musobaqa tugaganda g'oliblarga shu fonddan to'lanadi;
  3) to'lanmay qolgan qism (ishtirokchi yetmagan, o'rin bo'sh) ustozga qaytadi;
  4) musobaqa o'chirilsa — bron to'liq qaytariladi.

Barcha o'zgarishlar shartli UPDATE bilan bajariladi (compare-and-swap), shuning
uchun parallel so'rovlar bir xil coinni ikki marta sarflay/qaytara olmaydi.
"""
from django.db import transaction
from django.db.models import F
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import Competition

PLACE_NAMES = ("1-o'rin 🥇", "2-o'rin 🥈", "3-o'rin 🥉")


class EscrowError(Exception):
    """Foydalanuvchiga ko'rsatiladigan xato (masalan, balans yetarli emas)."""


def _prizes(competition):
    return (competition.coin_1st, competition.coin_2nd, competition.coin_3rd)


@transaction.atomic
def reserve(competition, funder, amount):
    """Yangi ustoz musobaqasi uchun fondni ustoz hisobidan bron qilish."""
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
    """Sovrinlar o'zgarganda bronni yangi fondga moslash.

    Oshsa — farq ustozdan qo'shimcha yechiladi; kamaysa — farq qaytariladi.
    """
    current = competition.prize_reserved
    delta = new_total - current
    if delta == 0:
        return
    if delta > 0:
        if not funder.try_spend_coins(delta, f"Musobaqa sovrin fondi (qo'shimcha bron): {competition.title}"):
            raise EscrowError(
                f"Balansingiz yetarli emas: qo'shimcha {delta} coin kerak, "
                f"hisobingizda {funder.coins} coin."
            )
    updated = Competition.objects.filter(
        pk=competition.pk, prize_reserved=current, coins_awarded=False,
    ).update(prize_reserved=new_total)
    if not updated:
        # Bron shu orada o'zgargan (parallel so'rov yoki hisob-kitob) — tranzaksiya
        # bekor bo'ladi va yechilgan coin ham qaytadi.
        raise EscrowError("Sovrin fondi shu orada o'zgardi. Sahifani yangilab, qayta urinib ko'ring.")
    if delta < 0:
        funder.add_coins(-delta, f"Musobaqa sovrin fondi kamaytirildi: {competition.title}")
    competition.prize_reserved = new_total


@transaction.atomic
def refund(competition, reason=None):
    """Bron qilingan fondni to'liq ustozga qaytarish. Qaytarilgan miqdorni beradi."""
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


def pay_winners(competition, top_attempts):
    """G'oliblarga to'lash. Chaqiruvchi tranzaksiya ichida bo'lishi shart.

    Qaytaradi: [(attempt, place_index, amount), ...] — faqat haqiqatan to'langanlar.
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
        # Kursni tugatgan o'quvchiga coin qo'shilmaydi (add_coins jim o'tkazib
        # yuboradi) — bunday o'rin to'lanmagan hisoblanadi va fondda qoladi.
        if amount <= 0 or user.is_finished:
            continue
        user.add_coins(amount, f"Musobaqa g'olibi: {competition.title} ({PLACE_NAMES[idx]})")
        paid.append((attempt, idx, amount))
        if teacher_funded:
            budget -= amount

    if teacher_funded:
        Competition.objects.filter(pk=competition.pk).update(prize_reserved=budget)
        competition.prize_reserved = budget
        if budget > 0:
            refund(competition, f"Musobaqa sovrin fondining ishlatilmagan qismi: {competition.title}")
    return paid


def notify_winners(competition, winners):
    """Sayt ichidagi xabar + Telegram. Tranzaksiyadan tashqarida chaqiriladi."""
    from accounts.models import Message
    from telegram_bot.utils import notify_user, notify_group

    is_word = competition.game.game_type == 'word_builder'
    lines = []
    for attempt, idx, amount in winners:
        user, place = attempt.user, PLACE_NAMES[idx]
        Message.objects.create(
            title=f"🏆 Tabriklaymiz! {place}",
            content=(
                f"Siz \"{competition.title}\" musobaqasida {place} ni egallashga muvaffaq bo'ldingiz! "
                f"Sizga {amount} coin mukofot berildi. Zo'r natija! 🎉"
            ),
            message_type='achievement',
            recipient=user,
        )
        if user.telegram_id:
            notify_user(
                user.telegram_id,
                f"🏆 <b>Tabriklaymiz!</b>\n\n"
                f"Siz <b>\"{competition.title}\"</b> musobaqasida <b>{place}</b> ni egallashga muvaffaq bo'ldingiz!\n\n"
                f"🪙 Mukofot: <b>+{amount} coin</b>\n\n"
                f"🎉 Zo'r natija! Davom eting!"
            )
        score = attempt.total_score if is_word else attempt.score
        lines.append(f"{place} — <b>{user.full_name}</b> ({score} ball, +{amount} coin)")

    notify_group(
        f"🏆 <b>Musobaqa natijalari!</b>\n\n"
        f"🎮 <b>{competition.title}</b>\n"
        f"📋 O'yin: {competition.game.title}\n\n"
        + "\n".join(lines) +
        f"\n\n🎉 G'oliblarni tabriklaymiz!"
    )


@receiver(pre_delete, sender=Competition, dispatch_uid='games_refund_prize_on_delete')
def _refund_on_delete(sender, instance, **kwargs):
    """Qaysi yo'l bilan o'chirilmasin (admin, ustoz, o'yin bilan kaskad) —
    hisob-kitob qilinmagan bron ustozga qaytadi."""
    if instance.prize_reserved and not instance.coins_awarded:
        refund(instance, f"Musobaqa o'chirildi, sovrin fondi qaytarildi: {instance.title}")
