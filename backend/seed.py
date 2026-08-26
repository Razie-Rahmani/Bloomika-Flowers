from database import get_connection, init_db

init_db()
conn = get_connection()

conn.execute("""
    INSERT INTO products (name, price, category)
    VALUES (?, ?, ?)
""", ("Black Rose Bouquet", 250000, "under_300k"))
conn.execute("""
    INSERT INTO products (name, price, category)
    VALUES (?, ?, ?)
""", ("White Lily Arrangement", 450000, "300k_to_500k"))

conn.commit()
conn.close()
print("Seeded!")