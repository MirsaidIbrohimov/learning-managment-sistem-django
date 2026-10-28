"""Özbekiston telefon raqamini tekşiriş va yagona körinişga keltiriş."""
import re

UZ_PHONE_ERROR = "Faqat Özbekiston raqami: +998 dan keyin 9 ta raqam (masalan +998 90 123 45 67)."


def normalize_uz_phone(raw):
    """'+998 90 123-45-67', '998901234567', '901234567' → '+998901234567'. Notöğri bölsa None."""
    digits = re.sub(r'\D', '', raw or '')
    if len(digits) == 12 and digits.startswith('998'):
        digits = digits[3:]
    if len(digits) != 9 or digits[0] == '0':
        return None
    return '+998' + digits


def local_part(phone):
    """'+998901234567' → '901234567' (forma maydoni uçun)."""
    digits = re.sub(r'\D', '', phone or '')
    return digits[3:] if len(digits) == 12 and digits.startswith('998') else digits
