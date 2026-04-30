import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import PollAnswer

BOT_TOKEN = "8524186055:AAGVAarqtDP8UgDrWZmsaKtBIIsqS30v4Ss"

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher()

QUESTIONS = [
    {
        "question": "❓ Python'da list va tuple'ning asosiy farqi nima?",
        "options": [
            "Hech qanday farq yo'q",
            "List o'zgaruvchan (mutable), Tuple o'zgarmas (immutable)",
            "Tuple faqat raqamlar saqlaydi",
            "List tezroq ishlaydi",
        ],
        "correct_option_id": 1,
        "explanation": "✅ List — mutable (o'zgartiriladi). Tuple — immutable (o'zgartirilmaydi).",
        "open_period": 30,
    },
    {
        "question": "❓ Python'da dictionary yaratish uchun qaysi belgi?",
        "options": ["[ ]", "( )", "{ }", "< >"],
        "correct_option_id": 2,
        "explanation": "✅ Dictionary {} figurali qavslar bilan yaratiladi.",
        "open_period": 30,
    },
]

# Foydalanuvchi sessiyalari (qaysi savolda ekanligi)
sessions: dict = {}


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🎯 <b>Viktorina Botiga Xush Kelibsiz!</b>\n\n"
        "Bu bot Telegram'ning <b>native quiz poll</b> ishlatadi.\n"
        "Har savolda o'ngda <b>doira timer</b> avtomatik chiqadi — "
        "xuddi siz ko'rmoqchi bo'lgan ko'rinishda!\n\n"
        "▶️ /test — 1 ta savol\n"
        "▶️ /quiz — Barcha savollar",
        parse_mode="HTML",
    )


@dp.message(Command("test"))
async def cmd_test(message: types.Message):
    """Bitta savol — Telegram native quiz poll + open_period = doira timer"""
    q = QUESTIONS[0]
    await message.answer_poll(
        question=q["question"],
        options=q["options"],
        type="quiz",
        correct_option_id=q["correct_option_id"],
        explanation=q["explanation"],
        is_anonymous=False,
        open_period=q["open_period"],   # ← BU doira timerni yoqadi!
    )


@dp.message(Command("quiz"))
async def cmd_quiz(message: types.Message):
    """Barcha savollar navbatma-navbat"""
    user_id = message.from_user.id
    sessions[user_id] = 0
    await send_question(message.chat.id, user_id, 0)


async def send_question(chat_id: int, user_id: int, index: int):
    if index >= len(QUESTIONS):
        await bot.send_message(chat_id, "🏁 <b>Test yakunlandi!</b>", parse_mode="HTML")
        return

    q = QUESTIONS[index]
    n = index + 1
    total = len(QUESTIONS)

    # Savol raqamini oldindan yuborish
    await bot.send_message(
        chat_id,
        f"📌 <b>Savol {n}/{total}</b>",
        parse_mode="HTML",
    )

    await bot.send_poll(
        chat_id=chat_id,
        question=q["question"],
        options=q["options"],
        type="quiz",
        correct_option_id=q["correct_option_id"],
        explanation=q["explanation"],
        is_anonymous=False,
        open_period=q["open_period"],
    )

    # Keyingi savol uchun kutish
    if index + 1 < len(QUESTIONS):
        await asyncio.sleep(q["open_period"] + 2)
        sessions[user_id] = index + 1
        await send_question(chat_id, user_id, index + 1)
    else:
        await asyncio.sleep(q["open_period"] + 1)
        await bot.send_message(chat_id, "🏁 <b>Test yakunlandi! Tabriklaymiz!</b>", parse_mode="HTML")


@dp.poll_answer()
async def on_answer(poll_answer: PollAnswer):
    """Javob qayd qilish"""
    logging.info(
        f"User: {poll_answer.user.first_name} | "
        f"Javob: {poll_answer.option_ids}"
    )


async def main():
    logging.basicConfig(level=logging.INFO)
    print("✅ Bot ishga tushdi...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())