from database import get_connection, init_db

init_db()
conn = get_connection()

cur = conn.cursor()
cur.execute("""
    INSERT INTO products (name, price, category)
    VALUES (%s, %s, %s)
""", ("Black Rose Bouquet", 250000, "under_300k"))
cur.execute("""
    INSERT INTO products (name, price, category)
    VALUES (%s, %s, %s)
""", ("White Lily Arrangement", 450000, "300k_to_500k"))

conn.commit()
conn.close()
print("Seeded!")