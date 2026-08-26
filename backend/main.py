from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from database import get_connection, init_db
from pydantic import BaseModel
from typing import Optional
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import json

from aiogram import Bot
import os
from dotenv import load_dotenv

load_dotenv()
bot = Bot(token = os.getenv("BOT_TOKEN"))
ADMIN_ID = os.getenv("ADMIN_ID")

class Orders(BaseModel):
    customer_name: str
    address: str
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


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

@app.get("/products")
def get_products():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/products/")
async def add_new_product(products: Product):
    conn = get_connection()
    cursor = conn.execute("""
        INSERT INTO products (name, price, category)
        VALUES (?, ?, ?)
    """, (products.name, products.price, products.category))
    conn.commit()
    product_id = cursor.lastrowid
    conn.close()
    return {"product_id": product_id, "name": products.name, "price": products.price, "category": products.category}

@app.patch("/products/{product_id}")
def edit_product(product_id: int, update: ProductUpdate):
    conn = get_connection()
    set_clauses = []
    values = []
    if update.name is not None:
        set_clauses.append("name = ?")
        values.append(update.name)
    if update.price is not None:
        set_clauses.append("price = ?")
        values.append(update.price)
    if update.category is not None:
        set_clauses.append("category = ?")
        values.append(update.category)
    clause_string = ", ".join(set_clauses)
    values.append(product_id)
    conn.execute(f"UPDATE products SET {clause_string} WHERE id = ?", values)
    conn.commit()
    updated_product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id, )).fetchone()
    conn.close()
    return dict(updated_product)

@app.post("/orders/")
async def send_orders(orders: Orders):
    conn = get_connection()
    cursor = conn.execute("""
        INSERT INTO orders (customer_name, address, items, total_price, status)
        VALUES (?, ?, ?, ?, ?)
    """, (orders.customer_name, orders.address, json.dumps(orders.items), orders.total_price, "pending payment"))
    conn.commit()
    order_id = cursor.lastrowid
    conn.close()
    return {"order_id": order_id, "status": "pending payment", "total_price": orders.total_price}

@app.get("/orders")
def get_orders():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM orders").fetchall()
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
    conn.execute("""
        UPDATE orders SET status = ? WHERE id = ?
    """, (update.status, order_id))
    conn.commit()
    new_stat = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id, )).fetchone()
    conn.close()
    return dict(new_stat)

@app.post("/orders/{order_id}/payment")
async def upload_payments(order_id: int, receipt: UploadFile = File(...)):
    contents = await receipt.read()
    file_path = f"payment_uploads/receipt_{order_id}.jpg"
    with open(file_path, "wb") as f:
        f.write(contents)
    conn = get_connection()
    conn.execute("""
        UPDATE orders SET status = ? WHERE id = ?    
    """, ("pending_confirmation", order_id))
    conn.commit()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard= [
            [InlineKeyboardButton(text="✅ Confirm", callback_data=f"confirm_{order_id}")],
            [InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_{order_id}")]
        ]
    )
    await bot.send_message(ADMIN_ID, f"Payment received for order #{order_id} from {order['customer_name']} with {order['customer_telegram_id']}\nTotal: {order['total_price']}\nPlease review the receipt.", reply_markup=keyboard)
    return{"status": "submitted", "message": "Your request has been submitted. Please wait for confirmation."}