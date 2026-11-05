"""Coin mukofotlari qoidalari — barça joylar şu yerdagi qiymatlardan foydalanadi.

- Uy vazifasi: har bir ball uçun 20 coin (10 ball -> 200 coin).
- Test: har bir töğri javob uçun 5 coin + testdan ötilsa 100 coin bonus
  (15 talik testda 10 ta töğri va ötdi -> 10*5 + 100 = 150 coin).
- Premium: har kuni birinçi kiriş uçun 300 coin.
"""

HOMEWORK_COINS_PER_POINT = 20
HOMEWORK_MAX_GRADE = 10
HOMEWORK_MAX_COINS = HOMEWORK_COINS_PER_POINT * HOMEWORK_MAX_GRADE

TEST_COINS_PER_CORRECT = 5
TEST_PASS_BONUS = 100

PREMIUM_DAILY_LOGIN_COINS = 300


def homework_coins(grade):
    """Baho (1-10) böyiça vazifa uçun beriladigan coin."""
    try:
        grade = int(grade or 0)
    except (TypeError, ValueError):
        return 0
    grade = max(0, min(grade, HOMEWORK_MAX_GRADE))
    return grade * HOMEWORK_COINS_PER_POINT


def test_coins(correct, passed):
    """Test uçun coin: töğri javoblar * 5 + ötilsa 100."""
    correct = max(0, int(correct or 0))
    return correct * TEST_COINS_PER_CORRECT + (TEST_PASS_BONUS if passed else 0)


def test_coin_reason(title, correct, passed):
    """Coin tarixida körinadigan izoh."""
    parts = f"{correct} ta töğri × {TEST_COINS_PER_CORRECT}"
    if passed:
        parts += f" + {TEST_PASS_BONUS} ötgani uçun"
    return f"Test: {title} ({parts})"[:255]


def award_premium_daily_bonus(user):
    """Premium öquvçiga kuniga bir marta 300 coin; berilgan miqdorni qaytaradi.

    `last_daily_login` şartli UPDATE bilan belgilanadi — bir vaqtda kelgan
    ikki login (sayt + desktop) bonusni ikki marta bera olmaydi.
    """
    from django.utils import timezone

    if not getattr(user, 'is_premium', False):
        return 0
    today = timezone.now().date()
    claimed = type(user).objects.filter(pk=user.pk).exclude(
        last_daily_login=today).update(last_daily_login=today)
    user.last_daily_login = today
    if not claimed:
        return 0
    user.add_coins(PREMIUM_DAILY_LOGIN_COINS, "Premium kunlik bonus")
    return PREMIUM_DAILY_LOGIN_COINS
