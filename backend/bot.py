from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.filters import Command
from dotenv import load_dotenv
import os
import asyncio
import httpx

# ============================================
# TODO — NOT YET IMPLEMENTED (depends on frontend)
# ============================================
# When admin confirms/rejects an order (see handle_decision below),
# the customer should ALSO get a Telegram push notification.
# This currently does NOT happen — handle_decision only replies to admin.
#
# Blocked on: orders table needs a `customer_telegram_id` column.
# This id comes from Telegram's Mini App launch data
# (Telegram.WebApp.initDataUnsafe.user.id on the frontend side),
# not something the customer types manually.
#
# Once that column + frontend capture exist:
# 1. In handle_decision, after the PATCH call succeeds,
#    fetch the order's customer_telegram_id (via a GET or a new endpoint)
# 2. await bot.send_message(customer_telegram_id, f"Your order #{order_id} was {new_status}!")
# ============================================

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
API_URL = "http://127.0.0.1:8000"

bot = Bot(token=TOKEN)
dp = Dispatcher()

async def main_menu(message: Message):
    if message.from_user.id == ADMIN_ID:
        text = "Bloomika admin bot running. You'll be notified here when orders come in."
        keyboard = None  # maybe some admin-specific keyboard later
    else:
        text = "Welcome to Bloomika! 🌸 Open the shop to browse and order."
        keyboard = InlineKeyboardMarkup(
            inline_keyboard = [
                [InlineKeyboardButton(text = "FAQ", callback_data = "faq_menu")],
                [InlineKeyboardButton(text = "Contact Us", callback_data = "contact_us")],
                [InlineKeyboardButton(text = "Open Shop", web_app = WebAppInfo(url = "https://example.com"))]
            ]
        )

    await message.answer(text, reply_markup = keyboard)


@dp.message(Command("start"))
async def start(message: Message):
    await main_menu(message)

@dp.callback_query(F.data == "faq_menu")
async def show_faq_menu(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard = [
            [InlineKeyboardButton(text = "Is it available?", callback_data = "faq_availability")],
            [InlineKeyboardButton(text = "What's the price?", callback_data = "faq_price")],
            [InlineKeyboardButton(text = "Do you deliver?", callback_data = "faq_delivery")],
        ]
    )
    await callback.message.answer("Choose a question:", reply_markup = keyboard)
    await callback.answer()

FAQ_ANSWERS = {
    "faq_availability": "بله، محصولات موجود است!",
    "faq_price": "قیمت‌ها داخل مینی‌اپ مشخص شده.",
    "faq_delivery": "بله، ارسال داریم.",
}

@dp.callback_query(F.data.startswith("faq_") & ~F.data.contains("menu"))
async def answer_faq(callback: CallbackQuery):
    answer = FAQ_ANSWERS.get(callback.data)
    await callback.message.answer(answer)
    await callback.answer()

@dp.callback_query(F.data.startswith("confirm_") | F.data.startswith("reject_"))
async def handle_decision(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Not authorized.", show_alert=True)
        return

    action, order_id = callback.data.split("_")
    new_status = "confirmed" if action == "confirm" else "rejected"

    async with httpx.AsyncClient() as client:
        await client.patch(f"{API_URL}/orders/{order_id}", json={"status": new_status})

    await callback.message.answer(f"Order #{order_id} {new_status}. Customer notified.")
    await callback.answer()

# TODO: notify customer once customer_telegram_id is populated (see top-of-file note)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())