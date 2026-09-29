import os

from dotenv import load_dotenv
from supabase import create_client
from database import get_db


load_dotenv()


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv(
    "SUPABASE_SERVICE_ROLE_KEY"
)
SUPABASE_STORAGE_BUCKET = os.getenv(
    "SUPABASE_STORAGE_BUCKET",
    "product-images"
)


if not SUPABASE_URL:
    raise RuntimeError(
        "SUPABASE_URL is not configured."
    )


if not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError(
        "SUPABASE_SERVICE_ROLE_KEY is not configured."
    )


supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY
)


print()
print("=" * 60)
print("PRODUCT IMAGE URL MIGRATION")
print("=" * 60)
print()


conn = get_db()


products = conn.execute("""
    SELECT
        id,
        name,
        image
    FROM products
    WHERE image IS NOT NULL
      AND TRIM(image) <> ''
    ORDER BY id
""").fetchall()


print(
    f"Found {len(products)} product(s) with images."
)
print()


updated = 0
skipped = 0


for product in products:

    product_id = product["id"]
    product_name = product["name"]
    image_value = str(
        product["image"]
    ).strip()


    print(
        f"Product #{product_id}: {product_name}"
    )
    print(
        f"Current image: {image_value}"
    )


    # Already migrated
    if image_value.startswith(
        "http://"
    ) or image_value.startswith(
        "https://"
    ):

        print(
            "Status: Already a URL - skipped."
        )
        print()

        skipped += 1

        continue


    image_filename = image_value


    public_url = supabase.storage.from_(
        SUPABASE_STORAGE_BUCKET
    ).get_public_url(
        image_filename
    )


    if not public_url:

        print(
            "ERROR: Could not generate public URL."
        )
        print()

        continue


    print(
        f"New image URL: {public_url}"
    )


    conn.execute("""
        UPDATE products
        SET image = ?
        WHERE id = ?
    """, (
        public_url,
        product_id
    ))


    conn.commit()


    print(
        "Status: Updated successfully."
    )
    print()

    updated += 1


conn.close()


print("=" * 60)
print("MIGRATION COMPLETE")
print("=" * 60)
print(
    f"Updated: {updated}"
)
print(
    f"Skipped: {skipped}"
)
print()