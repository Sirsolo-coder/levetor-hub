import sqlite3


DATABASE = "levetor.db"


def get_db():
    conn = sqlite3.connect(DATABASE)

    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    conn = get_db()

    cursor = conn.cursor()

    # =====================================================
    # PRODUCTS TABLE
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            category TEXT NOT NULL,

            brand TEXT,

            model TEXT,

            description TEXT,

            price REAL NOT NULL,

            stock INTEGER DEFAULT 0,

            image TEXT,

            condition TEXT DEFAULT 'New',

            warranty TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )
    """)

    # =====================================================
    # CUSTOMERS TABLE
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            fullname TEXT NOT NULL,

            email TEXT,

            phone TEXT NOT NULL,

            address TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )
    """)

    # =====================================================
    # CUSTOMER AUTHENTICATION
    # =====================================================

    try:
        cursor.execute("""
            ALTER TABLE customers
            ADD COLUMN password_hash TEXT
        """)
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("""
            ALTER TABLE customers
            ADD COLUMN reset_token TEXT
        """)
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("""
            ALTER TABLE customers
            ADD COLUMN reset_token_expiry TIMESTAMP
        """)
    except sqlite3.OperationalError:
        pass

    # =====================================================
    # PUSH NOTIFICATIONS
    # =====================================================

    try:
        cursor.execute("""
            ALTER TABLE customers
            ADD COLUMN fcm_token TEXT
        """)
    except sqlite3.OperationalError:
        pass

    # =====================================================
    # GOOGLE AUTHENTICATION
    # =====================================================

    try:
        cursor.execute("""
            ALTER TABLE customers
            ADD COLUMN google_id TEXT
        """)
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("""
            ALTER TABLE customers
            ADD COLUMN auth_provider TEXT DEFAULT 'password'
        """)
    except sqlite3.OperationalError:
        pass

    # =====================================================
    # ORDERS TABLE
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            customer_id INTEGER,

            total_amount REAL NOT NULL,

            payment_status TEXT DEFAULT 'Pending',

            order_status TEXT DEFAULT 'Pending',

            paystack_reference TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (customer_id)
            REFERENCES customers(id)

        )
    """)

    # =====================================================
    # PAYSTACK REFERENCE COLUMN
    # =====================================================

    try:
        cursor.execute("""
            ALTER TABLE orders
            ADD COLUMN paystack_reference TEXT
        """)
    except sqlite3.OperationalError:
        pass

    # =====================================================
    # ORDER ITEMS TABLE
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            order_id INTEGER,

            product_id INTEGER,

            quantity INTEGER NOT NULL,

            price REAL NOT NULL,

            FOREIGN KEY (order_id)
            REFERENCES orders(id),

            FOREIGN KEY (product_id)
            REFERENCES products(id)

        )
    """)

    # =====================================================
    # NOTIFICATIONS TABLE
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            customer_id INTEGER NOT NULL,

            title TEXT NOT NULL,

            body TEXT NOT NULL,

            notification_type TEXT DEFAULT 'general',

            data TEXT,

            is_read INTEGER DEFAULT 0,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (customer_id)
            REFERENCES customers(id)

        )
    """)

    # =====================================================
    # SAVE CHANGES
    # =====================================================

    conn.commit()

    conn.close()


# =========================================================
# RUN DATABASE INITIALIZATION
# =========================================================

if __name__ == "__main__":

    init_db()

    print(
        "Levetor Hub database initialized successfully."
    )