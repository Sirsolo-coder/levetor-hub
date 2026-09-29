import sqlite3
from database import get_db


SQLITE_DB = "levetor.db"


TABLES = [
    "customers",
    "products",
    "orders",
    "order_items",
    "notifications",
]


def get_sqlite_connection():
    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    return conn


def get_sqlite_rows(conn, table):
    rows = conn.execute(
        f"SELECT * FROM {table} ORDER BY id"
    ).fetchall()

    return [dict(row) for row in rows]


def insert_rows(pg_conn, table, rows):
    if not rows:
        print(f"{table}: 0 rows")
        return

    columns = list(rows[0].keys())

    column_sql = ", ".join(columns)
    placeholder_sql = ", ".join(["%s"] * len(columns))

    sql = f"""
        INSERT INTO {table}
        ({column_sql})
        VALUES ({placeholder_sql})
    """

    cursor = pg_conn.cursor()

    for row in rows:
        values = [row[column] for column in columns]
        cursor.execute(sql, values)

    cursor.close()

    print(f"{table}: {len(rows)} rows migrated")


def reset_sequence(pg_conn, table):
    cursor = pg_conn.cursor()

    sql = f"""
        SELECT setval(
            pg_get_serial_sequence('{table}', 'id'),
            COALESCE((SELECT MAX(id) FROM {table}), 1),
            true
        )
    """

    cursor.execute(sql)
    cursor.close()


def main():
    print("=" * 60)
    print("LEVETOR HUB - SQLITE TO POSTGRESQL MIGRATION")
    print("=" * 60)

    sqlite_conn = get_sqlite_connection()
    pg_conn = get_db()

    try:
        print("\nConnected to both databases successfully.")

        print("\nChecking existing PostgreSQL data...")

        for table in TABLES:
            row = pg_conn.execute(
                f"SELECT COUNT(*) AS count FROM {table}"
            ).fetchone()

            print(f"{table}: {row['count']} rows")

        print("\nIMPORTANT:")
        print("This migration will clear the selected PostgreSQL tables")
        print("and restore them from the local SQLite database.")
        print("Your local levetor.db will NOT be modified.")

        confirmation = input(
            "\nType MIGRATE to continue: "
        ).strip()

        if confirmation != "MIGRATE":
            print("\nMigration cancelled.")
            return

        print("\nStarting migration...\n")

        # Clear tables in dependency-safe order.
        for table in [
            "notifications",
            "order_items",
            "orders",
            "products",
            "customers",
        ]:
            pg_conn.execute(
                f"DELETE FROM {table}"
            )

        pg_conn.commit()

        print("Existing PostgreSQL data cleared.")

        # Read SQLite data.
        sqlite_data = {}

        for table in TABLES:
            sqlite_data[table] = get_sqlite_rows(
                sqlite_conn,
                table
            )

        # Insert parent tables first.
        for table in [
            "customers",
            "products",
            "orders",
            "order_items",
            "notifications",
        ]:
            insert_rows(
                pg_conn,
                table,
                sqlite_data[table]
            )

        pg_conn.commit()

        print("\nData insertion completed.")

        print("\nResetting PostgreSQL ID sequences...")

        for table in TABLES:
            reset_sequence(
                pg_conn,
                table
            )

        pg_conn.commit()

        print("ID sequences reset successfully.")

        print("\nVerifying migrated row counts...")

        all_ok = True

        for table in TABLES:
            sqlite_count = len(sqlite_data[table])

            pg_row = pg_conn.execute(
                f"SELECT COUNT(*) AS count FROM {table}"
            ).fetchone()

            pg_count = pg_row["count"]

            status = "OK" if sqlite_count == pg_count else "MISMATCH"

            print(
                f"{table}: SQLite={sqlite_count}, "
                f"PostgreSQL={pg_count} -> {status}"
            )

            if sqlite_count != pg_count:
                all_ok = False

        print("\n" + "=" * 60)

        if all_ok:
            print("MIGRATION SUCCESSFUL")
        else:
            print("MIGRATION COMPLETED WITH MISMATCHES")

        print("=" * 60)

    except Exception as e:
        pg_conn.rollback()

        print("\nMIGRATION FAILED")
        print("-" * 60)
        print(type(e).__name__)
        print(str(e))
        print("-" * 60)

        raise

    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()