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
        self.assertEqual(premium.pick_sticker("Oddiy bildirishnoma"), "messages")

    def test_successful_message_also_sends_sticker(self):
        response = Mock(status_code=200, text="")
        response.json.return_value = {"ok": True}
        session = Mock()
        session.post.side_effect = [response, response]

        original_disabled = premium._custom_emoji_disabled
        premium._custom_emoji_disabled = True
        try:
            result = premium.send_message(
                "token",
                123,
                "Hisobingizga kirildi!",
                session=session,
            )
        finally:
            premium._custom_emoji_disabled = original_disabled

        self.assertIs(result, response)
        self.assertEqual(session.post.call_count, 2)
        sticker_call = session.post.call_args_list[1]
        self.assertTrue(sticker_call.args[0].endswith("/sendSticker"))
        self.assertEqual(
            sticker_call.kwargs["json"]["sticker"],
            premium._STICKERS["success"],
        )
