import os
import re

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv


load_dotenv()


# =========================================================
# DATABASE CONFIGURATION
# =========================================================

DATABASE_URL = os.getenv("DATABASE_URL")


# =========================================================
# SQL COMPATIBILITY
# =========================================================

def convert_sql(sql):
    """
    Convert SQLite-style SQL syntax used by the existing
    Flask application into PostgreSQL-compatible syntax.
    """

    if not isinstance(sql, str):
        return sql

    # SQLite transaction mode.
    # PostgreSQL does not support BEGIN IMMEDIATE.
    sql = re.sub(
        r"^\s*BEGIN\s+IMMEDIATE\s*;?\s*$",
        "BEGIN",
        sql,
        flags=re.IGNORECASE,
    )

    # Existing app.py uses SQLite ? placeholders.
    # PostgreSQL/psycopg uses %s.
    sql = sql.replace("?", "%s")

    return sql


# =========================================================
# CURSOR WRAPPER
# =========================================================

class DatabaseCursor:
    """
    Compatibility wrapper around a psycopg cursor.

    It preserves the interface expected by the existing
    Flask application.
    """

    def __init__(self, cursor):
        self.cursor = cursor
        self.lastrowid = None

    def execute(self, sql, params=None):

        sql = convert_sql(sql)

        # -------------------------------------------------
        # INSERT compatibility
        # -------------------------------------------------
        #
        # Existing app.py uses cursor.lastrowid.
        #
        # PostgreSQL does not provide SQLite's lastrowid,
        # so automatically request the generated ID.
        #
        # Only do this for ordinary INSERT statements that
        # don't already contain RETURNING.
        # -------------------------------------------------

        stripped = sql.strip()

        if (
            stripped.upper().startswith("INSERT")
            and "RETURNING" not in stripped.upper()
        ):
            sql = stripped.rstrip(";") + " RETURNING id"

            if params is None:
                self.cursor.execute(sql)
            else:
                self.cursor.execute(sql, params)

            row = self.cursor.fetchone()

            if row is not None:
                try:
                    self.lastrowid = row["id"]
                except (TypeError, KeyError):
                    self.lastrowid = row[0]

            return self

        # -------------------------------------------------
        # Normal SQL
        # -------------------------------------------------

        if params is None:
            self.cursor.execute(sql)
        else:
            self.cursor.execute(sql, params)

        self.lastrowid = None

        return self

    def executemany(self, sql, seq_of_params):

        sql = convert_sql(sql)

        self.cursor.executemany(
            sql,
            seq_of_params
        )

        self.lastrowid = None

        return self

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def fetchmany(self, size=None):

        if size is None:
            return self.cursor.fetchmany()

        return self.cursor.fetchmany(size)

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def close(self):
        self.cursor.close()

    def __iter__(self):
        return iter(self.cursor)


# =========================================================
# CONNECTION WRAPPER
# =========================================================

class DatabaseConnection:
    """
    Compatibility wrapper around psycopg connection.

    This allows the existing Flask app to continue using:

        conn.execute(...)
        conn.commit()
        conn.close()

    without rewriting app.py.
    """

    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params=None):

        cursor = self.connection.cursor(
            row_factory=dict_row
        )

        wrapped = DatabaseCursor(cursor)

        wrapped.execute(
            sql,
            params
        )

        return wrapped

    def cursor(self):

        cursor = self.connection.cursor(
            row_factory=dict_row
        )

        return DatabaseCursor(cursor)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback
    ):

        if exc_type is not None:
            self.connection.rollback()

        self.connection.close()


# =========================================================
# GET DATABASE CONNECTION
# =========================================================

def get_db():

    if not DATABASE_URL:

        raise RuntimeError(
            "DATABASE_URL environment variable is not configured."
        )

    connection = psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row
    )

    return DatabaseConnection(connection)


# =========================================================
# INITIALIZE DATABASE
# =========================================================

def init_db():

    conn = get_db()

    try:

        # =================================================
        # CUSTOMERS
        # =================================================

        conn.execute("""
            CREATE TABLE IF NOT EXISTS customers (

                id SERIAL PRIMARY KEY,

                fullname TEXT NOT NULL,

                email TEXT,

                phone TEXT NOT NULL,

                address TEXT,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                password_hash TEXT,

                reset_token TEXT,

                reset_token_expiry TIMESTAMP,

                google_id TEXT,

                auth_provider TEXT DEFAULT 'password',

                fcm_token TEXT
            )
        """)

        # =================================================
        # CUSTOMER REFERRAL + STORE CREDIT MIGRATION
        # =================================================
        #
        # These ALTER TABLE statements are safe for the
        # existing PostgreSQL database because of
        # IF NOT EXISTS.
        #
        # Existing customers will receive:
        #
        #   referral_code = NULL
        #   store_credit_balance = 0
        #
        # Referral codes can later be generated for them.
        # =================================================

        conn.execute("""
            ALTER TABLE customers
            ADD COLUMN IF NOT EXISTS referral_code TEXT
        """)

        conn.execute("""
            ALTER TABLE customers
            ADD COLUMN IF NOT EXISTS store_credit_balance
            DOUBLE PRECISION NOT NULL DEFAULT 0
        """)

        # =================================================
        # PRODUCTS
        # =================================================

        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (

                id SERIAL PRIMARY KEY,

                name TEXT NOT NULL,

                category TEXT NOT NULL,

                brand TEXT,

                model TEXT,

                description TEXT,

                price DOUBLE PRECISION NOT NULL,

                stock INTEGER DEFAULT 0,

                image TEXT,

                condition TEXT DEFAULT 'New',

                warranty TEXT,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # =================================================
        # ORDERS
        # =================================================

        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (

                id SERIAL PRIMARY KEY,

                customer_id INTEGER,

                total_amount DOUBLE PRECISION NOT NULL,

                payment_status TEXT DEFAULT 'Pending',

                order_status TEXT DEFAULT 'Pending',

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                paystack_reference TEXT
            )
        """)

        # =================================================
        # REFERRALS
        #
        # One referrer can refer multiple customers.
        #
        # A referee can only belong to ONE referral
        # relationship.
        #
        # The UNIQUE constraint on referee_customer_id
        # prevents:
        #
        #   Customer A -> Customer B
        #   Customer A -> Customer B again
        #
        # and also prevents:
        #
        #   Customer A -> Customer B
        #   Customer C -> Customer B
        #
        # This rule is enforced by PostgreSQL itself,
        # not only by the Flutter application.
        # =================================================

        conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (

                id SERIAL PRIMARY KEY,

                referrer_customer_id INTEGER NOT NULL,

                referee_customer_id INTEGER NOT NULL UNIQUE,

                referral_code TEXT NOT NULL,

                status TEXT DEFAULT 'Pending',

                qualifying_amount DOUBLE PRECISION DEFAULT 0,

                referrer_reward DOUBLE PRECISION DEFAULT 1000,

                referee_reward DOUBLE PRECISION DEFAULT 1000,

                rewarded_at TIMESTAMP,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # =================================================
        # STORE CREDIT TRANSACTIONS
        #
        # Every credit movement is recorded here.
        #
        # This gives us an audit trail instead of relying
        # only on the balance stored on customers.
        # =================================================

        conn.execute("""
            CREATE TABLE IF NOT EXISTS store_credit_transactions (

                id SERIAL PRIMARY KEY,

                customer_id INTEGER NOT NULL,

                amount DOUBLE PRECISION NOT NULL,

                transaction_type TEXT NOT NULL,

                reference_type TEXT,

                reference_id INTEGER,

                description TEXT,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # =================================================
        # ORDER ITEMS
        #
        # Deliberately no foreign-key constraint here.
        #
        # Existing SQLite data contains an order item
        # referencing product_id = 1 while current products
        # contain IDs 5 and 6.
        #
        # We must preserve that historical record rather
        # than inventing a product.
        # =================================================

        conn.execute("""
            CREATE TABLE IF NOT EXISTS order_items (

                id SERIAL PRIMARY KEY,

                order_id INTEGER,

                product_id INTEGER,

                quantity INTEGER NOT NULL,

                price DOUBLE PRECISION NOT NULL
            )
        """)

        # =================================================
        # NOTIFICATIONS
        # =================================================

        conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (

                id SERIAL PRIMARY KEY,

                customer_id INTEGER NOT NULL,

                title TEXT NOT NULL,

                body TEXT NOT NULL,

                notification_type TEXT DEFAULT 'general',

                data TEXT,

                is_read INTEGER DEFAULT 0,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # =================================================
        # CUSTOMER INDEXES
        # =================================================

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_customers_email
            ON customers(email)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_customers_google_id
            ON customers(google_id)
        """)

        # =================================================
        # REFERRAL CODE INDEX
        #
        # Each active referral code must belong to only
        # one customer.
        #
        # NULL values are ignored by this partial index.
        # =================================================

        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_customers_referral_code
            ON customers(referral_code)
            WHERE referral_code IS NOT NULL
        """)

        # =================================================
        # ORDER INDEXES
        # =================================================

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_customer_id
            ON orders(customer_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_order_items_order_id
            ON order_items(order_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_order_items_product_id
            ON order_items(product_id)
        """)

        # =================================================
        # NOTIFICATION INDEX
        # =================================================

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_notifications_customer_id
            ON notifications(customer_id)
        """)

        # =================================================
        # REFERRAL INDEXES
        # =================================================

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_referrals_referrer
            ON referrals(referrer_customer_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_referrals_code
            ON referrals(referral_code)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_referrals_status
            ON referrals(status)
        """)

        # =================================================
        # STORE CREDIT INDEX
        # =================================================

        conn.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_store_credit_customer
            ON store_credit_transactions(customer_id)
        """)

        # =================================================
        # REFERRAL REWARD IDEMPOTENCY INDEX
        #
        # Prevents the same referral reward from being
        # credited twice to the same customer.
        #
        # Example:
        #
        # referral ID = 15
        # customer ID = 22
        #
        # Only one:
        #
        #   referral_reward / referral / 15
        #
        # transaction can exist for that customer.
        # =================================================

        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_store_credit_referral_reward
            ON store_credit_transactions(
                customer_id,
                transaction_type,
                reference_type,
                reference_id
            )
        """)

        # =================================================
        # COMMIT
        # =================================================

        conn.commit()

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()


# =========================================================
# RUN DATABASE INITIALIZATION
# =========================================================

if __name__ == "__main__":

    init_db()

    print(
        "Levetor Hub PostgreSQL database initialized successfully."
    )