from fastapi import FastAPI, UploadFile, File, Request, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from database import get_connection, init_db
from pydantic import BaseModel
from typing import Optional
import json

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Update, Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, BufferedInputFile
import httpx
import os
from dotenv import load_dotenv

load_dotenv()
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token = os.getenv("BOT_TOKEN"))
dp = Dispatcher()

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

class Orders(BaseModel):
    customer_telegram_id: str
    customer_name: str
    address: str
    postal_code: str
    phone_number: str
    items: dict
    total_price: int

class Product(BaseModel):
    name: str
    price: int
    category: str


class StatusUpdate(BaseModel):
    status: str

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[int] = None
    category: Optional[str] = None

init_db()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot.set_webhook(
        url=WEBHOOK_URL,
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=True,
    )
    yield
    await bot.delete_webhook()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        return {"ok": False}, 401

    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/products")
def get_products():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products")
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/products/")
async def add_new_product(products: Product):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO products (name, price, category)
        VALUES (%s, %s, %s)
        RETURNING id
    """, (products.name, products.price, products.category))
    conn.commit()
    product_id = cur.fetchone()["id"]
    conn.close()
    return {"product_id": product_id, "name": products.name, "price": products.price, "category": products.category}

@app.patch("/products/{product_id}")
def edit_product(product_id: int, update: ProductUpdate):
    conn = get_connection()
    set_clauses = []
    values = []
    if update.name is not None:
        set_clauses.append("name = %s")
        values.append(update.name)
    if update.price is not None:
        set_clauses.append("price = %s")
        values.append(update.price)
    if update.category is not None:
        set_clauses.append("category = %s")
        values.append(update.category)
    clause_string = ", ".join(set_clauses)
    values.append(product_id)
    cur = conn.cursor()
    cur.execute(f"UPDATE products SET {clause_string} WHERE id = %s", values)
    conn.commit()
    cur.execute("SELECT * FROM products WHERE id = %s", (product_id, ))
    updated_product = cur.fetchone()
    conn.close()
    return dict(updated_product)

@app.post("/orders/")
async def send_orders(orders: Orders):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO orders (customer_telegram_id, customer_name, address, phone_number, postal_code, items, total_price, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (orders.customer_telegram_id, orders.customer_name, orders.address, orders.phone_number, orders.postal_code, json.dumps(orders.items), orders.total_price, "pending payment"))
    conn.commit()
    order_id = cur.fetchone()["id"]
    conn.close()
    return {"order_id": order_id, "status": "pending payment", "items": orders.items, "total_price": orders.total_price}

@app.get("/orders")
def get_orders():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders")
    rows = cur.fetchall()
    conn.close()
    orders = []
    for row in rows:
        order = dict(row)
        order["items"] = json.loads(order["items"])
        orders.append(order)
    return orders

@app.patch("/orders/{order_id}")
def update_status(order_id: int, update: StatusUpdate):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE orders SET status = %s WHERE id = %s
    """, (update.status, order_id))
    conn.commit()
    cur.execute("SELECT * FROM orders WHERE id = %s", (order_id, ))
    new_stat = cur.fetchone()
    conn.close()
    return dict(new_stat)

@app.post("/orders/{order_id}/payment")
async def upload_payments(order_id: int, receipt: UploadFile = File(...)):
    contents = await receipt.read()

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE orders SET status = %s WHERE id = %s
    """, ("pending_confirmation", order_id))
    conn.commit()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
    order = cur.fetchone()
    conn.close()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    items = order["items"]
    if isinstance(items, str):
        items = json.loads(items)
    items_text = "\n".join(f"  • {name} × {qty}" for name, qty in items.items())

    caption = (
        f"🧾 New payment receipt — Order #{order_id}\n\n"
        f"👤 {order['customer_name']}\n"
        f"📞 {order['phone_number']}\n"
        f"📍 {order['address']} ({order['postal_code']})\n"
        f"🆔 Telegram ID: {order['customer_telegram_id']}\n\n"
        f"🛒 Items:\n{items_text}\n\n"
        f"💰 Total: {order['total_price']}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Confirm", callback_data=f"confirm_{order_id}")],
            [InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_{order_id}")]
        ]
    )

    try:
        photo = BufferedInputFile(contents, filename=f"receipt_{order_id}.jpg")
        await bot.send_photo(
            ADMIN_ID,
            photo=photo,
            caption=caption,
            reply_markup=keyboard
        )
    except Exception as e:
        print(f"Telegram notification failed: {e}")

    return{"status": "submitted", "message": "Your request has been submitted. Please wait for confirmation."}

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

    update_status(int(order_id), StatusUpdate(status=new_status))

    await callback.message.answer(f"Order #{order_id} {new_status}. Customer notified.")
    await callback.answer()