"""
Premium emoji va stikerlar moduli.

Telegram BOTLARI premium foydalanuvçi akkaunti kabi "premium stiker" yubora
olmaydi, lekin quyidagilar mumkin:

  1. Premium CUSTOM EMOJI (animatsiyali) — xabar matni içida HTML
     <tg-emoji emoji-id="..."> tegi orqali. Bu aynan premium stiker körinişini
     beradi va matn bilan birga ketadi.
  2. Oddiy STIKERLAR — sendSticker orqali alohida yuboriladi.

Bu modul ikkalasini ham markazlaştirib beradi va MUHIMI — xato bölsa ham
botni buzmaydi:

  * custom_emoji_id notöğri bölsa, Telegram xato qaytaradi -> biz avtomatik
    oddiy emoji bilan qayta yuboramiz (self-healing) va keyin custom emojini
    öçiramiz.
  * stiker file_id notöğri bölsa, jimgina ötkazib yuboriladi (stiker
    bezak — uni yöqolişi xabarni buzmaydi).

Haqiqiy, tekşirilgan ID larni serverda oliş uçun:
    python manage.py discover_telegram_assets
buyruğini işlating (Telegram serverga ulanadigan joyda). U `premium_assets.json`
faylini yaratadi va şu yerdagi ID lar ustuvor işlatiladi.
"""

import json
import os
import re
import threading

import requests
from django.conf import settings

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ASSETS_PATH = os.path.join(_BASE_DIR, "premium_assets.json")

# Custom emoji yuborişda xato çiqsa, jarayon davomida boşqa urinmaslik uçun
_custom_emoji_disabled = False
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Standart ID lar (örnatilgan). discover_telegram_assets bularni serverdan
# olingan tekşirilgan ID larga almaştiradi (premium_assets.json orqali).
# Har bir emoji -> animatsiyali premium custom emoji ID. Fallback sifatida
# özining unicode varianti işlatiladi, şuning uçun ID işlamasa ham
# foydalanuvçi oddiy emojini köradi.
# ---------------------------------------------------------------------------
_DEFAULT_CUSTOM_EMOJI = {
    "🎉": "5368324170671202286",
    "✅": "5427009714745517609",
    "❌": "5465665476971471368",
    "📚": "5188311512791393083",
    "📬": "5188551446128926090",
    "💰": "5217471307193593928",
    "📊": "5215706767009551699",
    "🤖": "5325547803936572038",
    "✉️": "5258085521903127230",
    "✍️": "5256599559612655660",
    "👋": "5436040291507247633",
    "🔑": "5226712339683136086",
    "⏳": "5451777529693568123",
    "🎁": "5253742976194763291",
    "🏆": "5391185172773030086",
    "⭐": "5206607081334906820",
    "📝": "5258029249460680834",
    "💬": "5258011829073811981",
    "🔔": "5413879192671230363",
    "⚠️": "5312241539987020022",
    "✨": "5249231733521367569",
    "❤️": "5199885118214255386",
    "🔥": "5188377234380954537",
    "📈": "5215706767009551699",
}

# Voqea -> stiker file_id. discover_telegram_assets buni töldiradi.
_DEFAULT_STICKERS = {
    "welcome": "",
    "success": "",
    "error": "",
    "books": "",
    "coins": "",
    "stats": "",
    "messages": "",
    "ai": "",
    "celebrate": "",
}


def _load_assets():
    custom_emoji = dict(_DEFAULT_CUSTOM_EMOJI)
    stickers = dict(_DEFAULT_STICKERS)
    try:
        if os.path.exists(_ASSETS_PATH):
            with open(_ASSETS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            custom_emoji.update(data.get("custom_emoji", {}) or {})
            stickers.update(data.get("stickers", {}) or {})
    except Exception:
        pass
    return custom_emoji, stickers


_CUSTOM_EMOJI, _STICKERS = _load_assets()


def _emoji_enabled():
    return getattr(settings, "TELEGRAM_USE_PREMIUM_EMOJI", True)


def _stickers_enabled():
    return getattr(settings, "TELEGRAM_USE_STICKERS", True)


# Eng uzun emojidan boşlab almaştiriş uçun (masalan, "✉️" "✉" dan oldin)
def _emoji_pattern():
    keys = sorted(_CUSTOM_EMOJI.keys(), key=len, reverse=True)
    return re.compile("|".join(re.escape(k) for k in keys))


_PATTERN = _emoji_pattern()
_TG_EMOJI_RE = re.compile(r"<tg-emoji[^>]*>(.*?)</tg-emoji>", re.DOTALL)


def tg_emoji(emoji_id, fallback):
    """Bitta premium custom emoji HTML tegini qaytaradi."""
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


def premiumize(text):
    """Matndagi oddiy emojilarni premium custom emoji bilan almaştiradi.

    Har bir custom emoji öz unicode variantini fallback sifatida saqlaydi,
    şuning uçun ID işlamasa foydalanuvçi oddiy emojini köradi.
    """
    global _custom_emoji_disabled
    if not text or _custom_emoji_disabled or not _emoji_enabled():
        return text
    # Allaqaçon tg-emoji bölsa, qayta öramaslik uçun belgilarni saqlaymiz
    if "<tg-emoji" in text:
        return text

    def _repl(m):
        ch = m.group(0)
        eid = _CUSTOM_EMOJI.get(ch)
        if not eid:
            return ch
        return tg_emoji(eid, ch)

    return _PATTERN.sub(_repl, text)


def strip_tg_emoji(text):
    """tg-emoji teglarini olib taşlab, faqat fallback emojini qoldiradi."""
    if not text:
        return text
    return _TG_EMOJI_RE.sub(lambda m: m.group(1), text)


def _is_custom_emoji_error(resp):
    """Xabar custom emoji sababli rad etilganmi?

    Bot (oddiy bot) custom emoji yubora olmaganda Telegram turli xil xatolar
    qaytaradi: yaroqsiz ID uçun "DOCUMENT_INVALID", ruxsat yöqligida
    "CUSTOM_EMOJI_INVALID" yoki "custom emoji" matnli xato, ba'zan entity
    xatolari. Bularning barçasini uşlab, custom emojisiz qayta yuboramiz.
    """
    try:
        if resp is None:
            return False
        try:
            if resp.status_code == 200 and resp.json().get("ok"):
                return False
        except Exception:
            pass
        body = (resp.text or "").upper()
        return any(marker in body for marker in (
            "CUSTOM_EMOJI",
            "CUSTOM EMOJI",
            "DOCUMENT_INVALID",
            "ENTITIES_TOO_LONG",
            "ENTITY",
        ))
    except Exception:
        return False


def send_message(bot_token, chat_id, text, reply_markup=None,
                 parse_mode="HTML", session=None, timeout=10, **extra):
    """Premium custom emojilarni matn içiga qöşib bitta xabar yuboradi.

    Mavjud requests.post(.../sendMessage, json={...}) çaqiruvlarining
    örnini bosadi. Custom emoji işlamasa oddiy emojiga qaytadi. Alohida
    stiker yuborilmaydi, şuning uçun foydalanuvçiga faqat bitta xabar keladi.
    """
    global _custom_emoji_disabled
    poster = session.post if session is not None else requests.post
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    final_text = premiumize(text)
    payload = {"chat_id": chat_id, "text": final_text, "parse_mode": parse_mode}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    payload.update(extra)

    try:
        resp = poster(url, json=payload, timeout=timeout)
    except Exception:
        return None

    # Custom emoji ID notöğri bölsa -> custom emojini öçirib qayta yuboramiz
    if _is_custom_emoji_error(resp) and final_text != text:
        with _lock:
            _custom_emoji_disabled = True
        payload["text"] = strip_tg_emoji(final_text)
        try:
            resp = poster(url, json=payload, timeout=timeout)
        except Exception:
            return None

    return resp


def send_sticker(bot_token, chat_id, event_or_file_id, session=None, timeout=10):
    """Stiker yuboradi. event nomi yoki töğridan-töğri file_id qabul qiladi.

    Stiker bezak — xato bölsa jimgina ötkazib yuboriladi.
    """
    if not _stickers_enabled():
        return None
    file_id = _STICKERS.get(event_or_file_id, event_or_file_id)
    if not file_id:
        return None
    poster = session.post if session is not None else requests.post
    url = f"https://api.telegram.org/bot{bot_token}/sendSticker"
    try:
        return poster(url, json={"chat_id": chat_id, "sticker": file_id},
                      timeout=timeout)
    except Exception:
        return None


def pick_sticker(text):
    """Xabar matniga qarab mos stiker tanlaydi.

    Har bir bot xabari stiker bilan borişi uçun maxsus tur topilmasa
    ``messages`` stikeri işlatiladi.
    """
    if not text:
        return "messages"
    t = text.lower()
    if any(k in text for k in ("Tabriklaymiz", "🎉", "🎁")):
        return "celebrate"
    if ("❌" in text or "xato" in t or "topilmadi" in t or
            "ulanmagan" in t or "hujum" in t or "bloklandi" in t or
            "rad etildi" in t or "notöğri" in t):
        return "error"
    if "✅" in text or "muvaffaqiyat" in t or "hisobingizga kirildi" in t:
        return "success"
    if "👋" in text or "/start" in t or "xuş kelibsiz" in t:
        return "welcome"
    if "📚" in text or "kitob" in t:
        return "books"
    if "💰" in text or "coin" in t:
        return "coins"
    if "📊" in text or "statistika" in t:
        return "stats"
    if "📬" in text or "xabar" in t:
        return "messages"
    if "🤖" in text or "ai çat" in t:
        return "ai"
    return "messages"
