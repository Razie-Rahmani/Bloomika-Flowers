import psycopg2
import psycopg2.extras
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products(
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            category TEXT NOT NULL,
            image_data BYTEA,
            image_mimetype TEXT
        )
    """)
    # Migrations for tables created before these columns existed.
    cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS image_data BYTEA")
    cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS image_mimetype TEXT")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders(
            id SERIAL PRIMARY KEY,
            customer_telegram_id TEXT,
            customer_name TEXT NOT NULL,
            phone_number TEXT,
            postal_code TEXT NOT NULL,
            address TEXT NOT NULL,
            items TEXT NOT NULL,
            total_price INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending payment'
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS faq(
            key TEXT PRIMARY KEY,
            question TEXT NOT NULL,
            answer TEXT NOT NULL
        )
    """)
    conn.commit()

    # Seed the FAQ table with the previously-hardcoded Q&A, only if empty,
    # so existing deployments migrate painlessly on first boot.
    cur.execute("SELECT COUNT(*) AS count FROM faq")
    if cur.fetchone()["count"] == 0:
        defaults = [
            ("faq_availability", "Is it available?", "بله، محصولات موجود است!"),
            ("faq_price", "What's the price?", "قیمت‌ها داخل مینی‌اپ مشخص شده."),
            ("faq_delivery", "Do you deliver?", "بله، ارسال داریم."),
        ]
        cur.executemany(
            "INSERT INTO faq (key, question, answer) VALUES (%s, %s, %s)",
            defaults
        )
        conn.commit()

    cur.close()
    conn.close()


def get_faqs():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM faq ORDER BY key")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_faq(key: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM faq WHERE key = %s", (key,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_faq_answer(key: str, answer: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE faq SET answer = %s WHERE key = %s", (answer, key))
    conn.commit()
    cur.execute("SELECT * FROM faq WHERE key = %s", (key,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def save_product_image(product_id: int, data: bytes, mimetype: str):
    """Stores a product photo directly in Postgres (no third-party CDN —
    avoids the OFAC-sanctions accessibility issue Cloudinary hit in Iran)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE products SET image_data = %s, image_mimetype = %s WHERE id = %s",
        (psycopg2.Binary(data), mimetype, product_id)
    )
    conn.commit()
    conn.close()


def get_product_image(product_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT image_data, image_mimetype FROM products WHERE id = %s", (product_id,))
    row = cur.fetchone()
    conn.close()
    if not row or row["image_data"] is None:
        return None
    return bytes(row["image_data"]), row["image_mimetype"] or "image/jpeg"