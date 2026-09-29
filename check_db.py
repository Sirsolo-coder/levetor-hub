import sqlite3

c = sqlite3.connect("levetor.db")

tables = c.execute("""
SELECT name
FROM sqlite_master
WHERE type = 'table'
AND name NOT LIKE 'sqlite_%'
ORDER BY name
""").fetchall()

print("\nDATABASE SCHEMA")
print("=" * 60)

for table in tables:
    name = table[0]

    print(f"\nTABLE: {name}")
    print("-" * 60)

    columns = c.execute(
        f'PRAGMA table_info("{name}")'
    ).fetchall()

    for column in columns:
        cid, column_name, data_type, not_null, default_value, primary_key = column

        print(
            f"  {column_name} | "
            f"type={data_type} | "
            f"not_null={not_null} | "
            f"default={default_value} | "
            f"pk={primary_key}"
        )

c.close()