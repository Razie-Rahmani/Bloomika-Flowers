import sqlite3

def get_connection():
    conn = sqlite3.connect("bloomika.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            category TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    conn.commit()
    conn.close()