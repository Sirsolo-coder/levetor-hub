import sqlite3

conn = sqlite3.connect("levetor.db")
conn.row_factory = sqlite3.Row

tables = [
    "customers",
    "products",
    "orders",
    "order_items",
    "notifications",
]

print()
print("DATABASE RECORD COUNTS")
print("=" * 60)

for table in tables:
    count = conn.execute(
        f"SELECT COUNT(*) FROM {table}"
    ).fetchone()[0]
    print(f"{table}: {count} rows")

print()
print("PRODUCTS")
print("=" * 60)

for row in conn.execute("SELECT * FROM products ORDER BY id"):
    print(dict(row))

print()
print("CUSTOMERS")
print("=" * 60)

for row in conn.execute("""
    SELECT id, fullname, email, phone, auth_provider, created_at
    FROM customers
    ORDER BY id
"""):
    print(dict(row))

print()
print("ORDERS")
print("=" * 60)

for row in conn.execute("SELECT * FROM orders ORDER BY id"):
    print(dict(row))

print()
print("ORDER ITEMS")
print("=" * 60)

for row in conn.execute("SELECT * FROM order_items ORDER BY id"):
    print(dict(row))

print()
print("NOTIFICATIONS")
print("=" * 60)

for row in conn.execute("""
    SELECT id, customer_id, title,
           notification_type, is_read, created_at
    FROM notifications
    ORDER BY id
"""):
    print(dict(row))

conn.close()

print()
print("DATABASE INSPECTION COMPLETE")