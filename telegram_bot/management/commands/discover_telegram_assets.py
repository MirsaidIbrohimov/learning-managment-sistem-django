"""
Telegram'dan HAQIQIY (tekşirilgan) custom_emoji_id va stiker file_id larni
yiğib, telegram_bot/premium_assets.json fayliga yozadi.

Bu buyruq Telegram serverga ulana oladigan joyda (sizning serveringizda yoki
lokal maşinangizda) işlatilişi kerak.

Işlatiş:

  # Custom emoji töplamidan (animatsiyali premium emoji) emoji->id xaritasi:
  python manage.py discover_telegram_assets --emoji-set <emoji_set_short_name>

  # Oddiy stiker töplamidan file_id larni körish/biriktirish:
  python manage.py discover_telegram_assets --sticker-set <sticker_set_short_name>

  # Bir neça töplam birga:
  python manage.py discover_telegram_assets \
      --emoji-set MySet --sticker-set MyStickers

Eslatma:
  * --emoji-set faqat "custom emoji" (custom_emoji_id bölgan) töplamlar uçun.
  * --sticker-set oddiy stikerlar uçun. Buyruq har bir stikerni emojisi bilan
    çiqaradi va emoji böyiça voqealarga (welcome/success/error...) avtomatik
    biriktirişga harakat qiladi. Keyin premium_assets.json'ni qölda
    tahrirlaşingiz mumkin.
"""

import json
import os

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

_BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_ASSETS_PATH = os.path.join(_BASE_DIR, "premium_assets.json")

# Stiker emojisi -> voqea nomi (avtomatik biriktiriş uçun taxminiy xarita)
_EVENT_BY_EMOJI = {
    "👋": "welcome", "🤝": "welcome",
    "✅": "success", "👍": "success", "🎯": "success",
    "❌": "error", "🚫": "error", "😢": "error", "😔": "error",
    "📚": "books", "📖": "books",
    "💰": "coins", "🪙": "coins", "💵": "coins",
    "📊": "stats", "📈": "stats",
    "📬": "messages", "✉️": "messages", "📩": "messages",
    "🤖": "ai",
    "🎉": "celebrate", "🥳": "celebrate", "🎊": "celebrate",
}


class Command(BaseCommand):
    help = "Telegram'dan haqiqiy custom_emoji_id va stiker file_id larni yiğadi"

    def add_arguments(self, parser):
        parser.add_argument("--emoji-set", action="append", default=[],
                            help="Custom emoji töplami short_name (bir neçta marta)")
        parser.add_argument("--sticker-set", action="append", default=[],
                            help="Oddiy stiker töplami short_name (bir neçta marta)")

    def _get_set(self, bot_token, name):
        url = f"https://api.telegram.org/bot{bot_token}/getStickerSet"
        resp = requests.get(url, params={"name": name}, timeout=15)
        data = resp.json()
        if not data.get("ok"):
            self.stderr.write(self.style.ERROR(
                f"  ✗ '{name}' olinmadi: {data.get('description')}"))
            return None
        return data["result"]

    def _load(self):
        if os.path.exists(_ASSETS_PATH):
            try:
                with open(_ASSETS_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"custom_emoji": {}, "stickers": {}}

    def _save(self, data):
        with open(_ASSETS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def handle(self, *args, **opts):
        bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            self.stderr.write(self.style.ERROR("TELEGRAM_BOT_TOKEN topilmadi (.env)."))
            return

        emoji_sets = opts["emoji_set"]
        sticker_sets = opts["sticker_set"]
        if not emoji_sets and not sticker_sets:
            self.stdout.write(self.style.WARNING(
                "Heç narsa berilmadi. Misol:\n"
                "  python manage.py discover_telegram_assets --emoji-set <name>\n"
                "  python manage.py discover_telegram_assets --sticker-set <name>"))
            return

        assets = self._load()
        assets.setdefault("custom_emoji", {})
        assets.setdefault("stickers", {})

        # --- Custom emoji töplamlari ---
        for name in emoji_sets:
            self.stdout.write(f"Custom emoji töplami: {name}")
            result = self._get_set(bot_token, name)
            if not result:
                continue
            count = 0
            for st in result.get("stickers", []):
                eid = st.get("custom_emoji_id")
                emoji = st.get("emoji")
                if eid and emoji:
                    assets["custom_emoji"][emoji] = str(eid)
                    count += 1
            self.stdout.write(self.style.SUCCESS(
                f"  ✓ {count} ta custom emoji qöşildi"))

        # --- Oddiy stiker töplamlari ---
        for name in sticker_sets:
            self.stdout.write(f"Stiker töplami: {name}")
            result = self._get_set(bot_token, name)
            if not result:
                continue
            for st in result.get("stickers", []):
                emoji = st.get("emoji", "")
                file_id = st.get("file_id")
                event = _EVENT_BY_EMOJI.get(emoji)
                tag = ""
                if event and not assets["stickers"].get(event):
                    assets["stickers"][event] = file_id
                    tag = f"  -> {event} ga biriktirildi"
                self.stdout.write(f"  {emoji}  {file_id}{tag}")

        self._save(assets)
        self.stdout.write(self.style.SUCCESS(
            f"\nSaqlandi: {_ASSETS_PATH}\n"
            f"  custom_emoji: {len(assets['custom_emoji'])} ta\n"
            f"  stickers: {sum(1 for v in assets['stickers'].values() if v)} ta biriktirilgan\n"
            "Kerak bölsa faylni qölda tahrirlab voqealarga töğri stiker biriktiring."))
