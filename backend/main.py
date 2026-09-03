from fastapi import FastAPI, UploadFile, File, Request, HTTPException, Query, Depends, Header
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from database import get_connection, init_db, get_faqs, get_faq, update_faq_answer, save_product_image, get_product_image
from pydantic import BaseModel
from typing import Optional
import json
from io import BytesIO

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Update, Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
import httpx
import os
from dotenv import load_dotenv

load_dotenv()
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token = os.getenv("BOT_TOKEN"))
dp = Dispatcher(storage=MemoryStorage())

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

# --- Admin REST auth (Issue C) ---
# Protects the write/admin-ish REST endpoints (add/edit product, list orders,
# change order status) from being hit anonymously now that the backend is a
# public Render URL. The bot's own admin panel below calls these functions
# directly in-process (plain Python calls), so it never goes through this
# check — this only gates real HTTP requests (curl, Postman, browser, etc).
ADMIN_API_TOKEN = os.getenv("ADMIN_API_TOKEN")

def verify_admin_token(x_admin_token: str = Header(None)):
    if not ADMIN_API_TOKEN:
        # Fail closed: if no token is configured, admin endpoints are
        # unreachable rather than silently wide open.
        raise HTTPException(status_code=503, detail="Admin auth not configured")
    if x_admin_token != ADMIN_API_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

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
    print("🔥 WEBHOOK_URL =", WEBHOOK_URL)
    print("🔥 WEBHOOK_SECRET configured =", bool(WEBHOOK_SECRET))
    result = await bot.set_webhook(
        url=WEBHOOK_URL,
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=True,
    )
    print("🔥 set_webhook result =", result) 
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
    cur.execute("SELECT id, name, price, category, (image_data IS NOT NULL) AS has_image FROM products")
    rows = cur.fetchall()
    conn.close()
    products = []
    for row in rows:
        p = dict(row)
        has_image = p.pop("has_image")
        p["image_url"] = f"/products/{p['id']}/photo" if has_image else None
        products.append(p)
    return products


@app.get("/products/{product_id}/photo")
def get_product_photo(product_id: int):
    result = get_product_image(product_id)
    if not result:
        raise HTTPException(status_code=404, detail="No photo for this product")
    data, mimetype = result
    return Response(content=data, media_type=mimetype)

@app.post("/products/", dependencies=[Depends(verify_admin_token)])
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

@app.patch("/products/{product_id}", dependencies=[Depends(verify_admin_token)])
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

@app.get("/orders", dependencies=[Depends(verify_admin_token)])
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

@app.patch("/orders/{order_id}", dependencies=[Depends(verify_admin_token)])
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

class AdminStates(StatesGroup):
    waiting_input = State()


def admin_menu_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛍 Edit Products", callback_data="admin_products")],
            [InlineKeyboardButton(text="📦 View All Orders", callback_data="admin_orders")],
            [InlineKeyboardButton(text="❓ Edit FAQ", callback_data="admin_faq")],
        ]
    )


async def main_menu(message: Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🌸 Bloomika admin panel", reply_markup=admin_menu_keyboard())
        return

    text = "Welcome to Bloomika! 🌸 Open the shop to browse and order."
    keyboard = InlineKeyboardMarkup(
        inline_keyboard = [
            [InlineKeyboardButton(text = "FAQ", callback_data = "faq_menu")],
            [InlineKeyboardButton(text = "Contact Us", callback_data = "contact_us")],
            [InlineKeyboardButton(text = "Open Shop", web_app = WebAppInfo(url = "https://bloomika-flowers-frontend.onrender.com"))]
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

@dp.callback_query(F.data.startswith("faq_") & ~F.data.contains("menu"))
async def answer_faq(callback: CallbackQuery):
    # Answers now live in the `faq` table (editable via the admin panel)
    # instead of the old hardcoded FAQ_ANSWERS dict.
    faq = get_faq(callback.data)
    answer = faq["answer"] if faq else "متأسفانه پاسخی برای این سوال ثبت نشده."
    await callback.message.answer(answer)
    await callback.answer()

@dp.callback_query(F.data.startswith("confirm_") | F.data.startswith("reject_") | F.data.startswith("deliver_"))
async def handle_decision(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Not authorized.", show_alert=True)
        return

    action, order_id = callback.data.split("_")
    status_map = {"confirm": "confirmed", "reject": "rejected", "deliver": "delivered"}
    new_status = status_map[action]

    update_status(int(order_id), StatusUpdate(status=new_status))

    await callback.message.answer(f"Order #{order_id} {new_status}.")
    await callback.answer()


# ============================================================
# Admin panel (Issue #4): Edit Products / View All Orders / Edit FAQ
# All handlers below double-check from_user.id == ADMIN_ID even though
# these buttons are only ever sent to the admin's own chat — cheap
# defense in depth, consistent with the existing confirm/reject handler.
# ============================================================

@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Not authorized.", show_alert=True)
        return
    await state.clear()
    await callback.message.answer("🌸 Bloomika admin panel", reply_markup=admin_menu_keyboard())
    await callback.answer()


# --- Products ---

@dp.callback_query(F.data == "admin_products")
async def admin_products_menu(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Not authorized.", show_alert=True)
        return

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products ORDER BY id")
    products = [dict(r) for r in cur.fetchall()]
    conn.close()

    buttons = [
        [InlineKeyboardButton(text=f"{p['name']} — {p['price']}", callback_data=f"pview_{p['id']}")]
        for p in products
    ]
    buttons.append([InlineKeyboardButton(text="➕ Add New Product", callback_data="padd")])
    buttons.append([InlineKeyboardButton(text="⬅️ Back", callback_data="admin_back")])

    await callback.message.answer(
        "🛍 Products — tap one to edit:" if products else "No products yet — add one below.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("pview_"))
async def admin_product_detail(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Not authorized.", show_alert=True)
        return

    product_id = int(callback.data.split("_")[1])
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, price, category, (image_data IS NOT NULL) AS has_image FROM products WHERE id = %s", (product_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        await callback.answer("Product not found.", show_alert=True)
        return

    product = dict(row)
    photo_status = "🖼 has a photo" if product["has_image"] else "🖼 no photo yet"
    text = f"🌸 {product['name']}\n💰 {product['price']}\n🏷 {product['category']}\n{photo_status}"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Name", callback_data=f"pedit_name_{product_id}")],
            [InlineKeyboardButton(text="✏️ Price", callback_data=f"pedit_price_{product_id}")],
            [InlineKeyboardButton(text="✏️ Category", callback_data=f"pedit_category_{product_id}")],
            [InlineKeyboardButton(text="🖼 Photo", callback_data=f"pedit_photo_{product_id}")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="admin_products")],
        ]
    )
    await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


@dp.callback_query(F.data.startswith("pedit_"))
async def admin_product_edit_prompt(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Not authorized.", show_alert=True)
        return

    _, field, product_id = callback.data.split("_")
    await state.update_data(product_id=int(product_id))

    if field == "photo":
        await state.set_state(AdminStates.waiting_input)
        await state.update_data(target="edit_photo")
        await callback.message.answer("Send the new photo:")
        await callback.answer()
        return

    prompts = {
        "name": "Send the new name:",
        "price": "Send the new price (numbers only):",
        "category": "Send the new category:",
    }
    await state.set_state(AdminStates.waiting_input)
    await state.update_data(target=f"edit_{field}")
    await callback.message.answer(prompts[field])
    await callback.answer()


@dp.callback_query(F.data == "padd")
async def admin_add_product_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Not authorized.", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_input)
    await state.update_data(target="add_name")
    await callback.message.answer("Send the new product's name:")
    await callback.answer()


# --- Orders ---

@dp.callback_query(F.data == "admin_orders")
async def admin_orders_menu(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Not authorized.", show_alert=True)
        return

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 20")
    orders = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not orders:
        await callback.message.answer("No orders yet.", reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Back", callback_data="admin_back")]]
        ))
        await callback.answer()
        return

    buttons = [
        [InlineKeyboardButton(text=f"#{o['id']} — {o['customer_name']} ({o['status']})", callback_data=f"oview_{o['id']}")]
        for o in orders
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Back", callback_data="admin_back")])
    await callback.message.answer("📦 Last 20 orders:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@dp.callback_query(F.data.startswith("oview_"))
async def admin_order_detail(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Not authorized.", show_alert=True)
        return

    order_id = int(callback.data.split("_")[1])
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        await callback.answer("Order not found.", show_alert=True)
        return

    order = dict(row)
    items = order["items"]
    if isinstance(items, str):
        items = json.loads(items)
    items_text = "\n".join(f"  • {name} × {qty}" for name, qty in items.items())

    text = (
        f"📦 Order #{order['id']} — {order['status']}\n\n"
        f"👤 {order['customer_name']}\n"
        f"📞 {order['phone_number']}\n"
        f"📍 {order['address']} ({order['postal_code']})\n"
        f"🆔 Telegram ID: {order['customer_telegram_id']}\n\n"
        f"🛒 Items:\n{items_text}\n\n"
        f"💰 Total: {order['total_price']}"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Confirm", callback_data=f"confirm_{order['id']}")],
            [InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_{order['id']}")],
            [InlineKeyboardButton(text="🚚 Mark Delivered", callback_data=f"deliver_{order['id']}")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="admin_orders")],
        ]
    )
    await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


# --- FAQ ---

@dp.callback_query(F.data == "admin_faq")
async def admin_faq_menu(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Not authorized.", show_alert=True)
        return

    faqs = get_faqs()
    buttons = [
        [InlineKeyboardButton(text=f"✏️ {f['question']}", callback_data=f"faqedit_{f['key']}")]
        for f in faqs
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Back", callback_data="admin_back")])
    await callback.message.answer("❓ FAQ — tap a question to edit its answer:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@dp.callback_query(F.data.startswith("faqedit_"))
async def admin_faq_edit_prompt(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Not authorized.", show_alert=True)
        return

    key = callback.data.split("faqedit_")[1]
    faq = get_faq(key)
    if not faq:
        await callback.answer("FAQ entry not found.", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_input)
    await state.update_data(target="faq_answer", faq_key=key)
    await callback.message.answer(f"Current answer:\n{faq['answer']}\n\nSend the new answer:")
    await callback.answer()


# --- Shared text-input handler for all of the above flows ---

@dp.message(AdminStates.waiting_input)
async def admin_text_input(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()
    target = data.get("target")

    # --- Photo-accepting steps ---
    if target in ("add_photo", "edit_photo"):
        if target == "add_photo" and message.text and message.text.strip().lower() == "skip":
            image_bytes = None
        elif message.photo:
            await message.answer("⏳ Saving photo…")
            largest = message.photo[-1]
            buf = BytesIO()
            await bot.download(largest, destination=buf)
            image_bytes = buf.getvalue()
        else:
            prompt = "Please send a photo, or type \"skip\" to leave it without one." if target == "add_photo" else "Please send a photo."
            await message.answer(prompt)
            return

        if target == "add_photo":
            new_product = await add_new_product(Product(
                name=data["new_name"], price=data["new_price"], category=data["new_category"]
            ))
            if image_bytes:
                save_product_image(new_product["product_id"], image_bytes, "image/jpeg")
            summary = f"✅ Added \"{data['new_name']}\" — {data['new_price']} ({data['new_category']})"
            summary += " with photo." if image_bytes else " (no photo)."
            await message.answer(summary, reply_markup=admin_menu_keyboard())
        else:  # edit_photo
            save_product_image(data["product_id"], image_bytes, "image/jpeg")
            await message.answer("✅ Photo updated.", reply_markup=admin_menu_keyboard())

        await state.clear()
        return

    # --- Text-only steps ---
    value = (message.text or "").strip()
    if not value:
        await message.answer("Please send text.")
        return

    if target == "edit_name":
        edit_product(data["product_id"], ProductUpdate(name=value))
        await message.answer("✅ Name updated.", reply_markup=admin_menu_keyboard())
        await state.clear()

    elif target == "edit_price":
        if not value.isdigit():
            await message.answer("That doesn't look like a number — send the price again:")
            return
        edit_product(data["product_id"], ProductUpdate(price=int(value)))
        await message.answer("✅ Price updated.", reply_markup=admin_menu_keyboard())
        await state.clear()

    elif target == "edit_category":
        edit_product(data["product_id"], ProductUpdate(category=value))
        await message.answer("✅ Category updated.", reply_markup=admin_menu_keyboard())
        await state.clear()

    elif target == "add_name":
        await state.update_data(new_name=value, target="add_price")
        await message.answer("Send the price (numbers only):")

    elif target == "add_price":
        if not value.isdigit():
            await message.answer("That doesn't look like a number — send the price again:")
            return
        await state.update_data(new_price=int(value), target="add_category")
        await message.answer("Send the category:")

    elif target == "add_category":
        await state.update_data(new_category=value, target="add_photo")
        await message.answer("Now send a photo of the product (or type \"skip\" to add it without one):")

    elif target == "faq_answer":
        update_faq_answer(data["faq_key"], value)
        await message.answer("✅ FAQ answer updated.", reply_markup=admin_menu_keyboard())
        await state.clear()

    else:
        await state.clear()