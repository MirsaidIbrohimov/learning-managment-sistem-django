from unittest.mock import Mock

from django.test import SimpleTestCase

from telegram_bot import premium


class PremiumTelegramTests(SimpleTestCase):
    def test_security_messages_get_matching_stickers(self):
        self.assertEqual(
            premium.pick_sticker("Brute-force hujumi aniqlandi!"),
            "error",
        )
        self.assertEqual(
            premium.pick_sticker("Hisobingizga kirildi!"),
            "success",
        )

    def test_uncategorized_message_gets_default_sticker(self):
        self.assertEqual(premium.pick_sticker("Oddiy bildirişnoma"), "messages")

    def test_successful_message_is_single_message_with_premium_emoji(self):
        response = Mock(status_code=200, text="")
        response.json.return_value = {"ok": True}
        session = Mock()
        session.post.return_value = response
        emoji = next(iter(premium._CUSTOM_EMOJI))

        original_disabled = premium._custom_emoji_disabled
        premium._custom_emoji_disabled = False
        try:
            result = premium.send_message(
                "token",
                123,
                f"{emoji} Hisobingizga kirildi!",
                session=session,
            )
        finally:
            premium._custom_emoji_disabled = original_disabled

        self.assertIs(result, response)
        session.post.assert_called_once()
        message_call = session.post.call_args
        self.assertTrue(message_call.args[0].endswith("/sendMessage"))
        self.assertIn("<tg-emoji", message_call.kwargs["json"]["text"])
