from database import get_db
from app import ensure_customer_referral_code, create_referral


conn = get_db()

try:
    conn.execute("BEGIN")

    # Create temporary test referrer
    referrer_cursor = conn.execute("""
        INSERT INTO customers
        (
            fullname,
            email,
            phone,
            address,
            password_hash
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        "Referral Test Referrer",
        "referrer_test@levetor.local",
        "08000000001",
        "Test Address",
        "test-password-hash"
    ))

    referrer_id = referrer_cursor.lastrowid

    referral_code = ensure_customer_referral_code(
        conn,
        referrer_id
    )

    print("TEST REFERRER ID:", referrer_id)
    print("REFERRAL CODE:", referral_code)

    # Create temporary test referee
    referee_cursor = conn.execute("""
        INSERT INTO customers
        (
            fullname,
            email,
            phone,
            address,
            password_hash
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        "Referral Test Referee",
        "referee_test@levetor.local",
        "08000000002",
        "Test Address",
        "test-password-hash"
    ))

    referee_id = referee_cursor.lastrowid

    # Create referral
    success, message = create_referral(
        conn,
        referrer_id,
        referee_id,
        referral_code
    )

    print("REFERRAL CREATED:", success)
    print("MESSAGE:", message)

    # Verify referral
    referral = conn.execute("""
        SELECT
            id,
            referrer_customer_id,
            referee_customer_id,
            referral_code,
            status,
            qualifying_amount,
            referrer_reward,
            referee_reward,
            rewarded_at
        FROM referrals
        WHERE referee_customer_id = ?
    """, (
        referee_id,
    )).fetchone()

    print("REFERRAL RECORD:", dict(referral))

    # Verify store credit
    referee_credit = conn.execute("""
        SELECT store_credit_balance
        FROM customers
        WHERE id = ?
    """, (
        referee_id,
    )).fetchone()

    print(
        "REFEREE STORE CREDIT:",
        referee_credit["store_credit_balance"]
    )

    # Test duplicate protection
    duplicate_success, duplicate_message = create_referral(
        conn,
        referrer_id,
        referee_id,
        referral_code
    )

    print("DUPLICATE REFERRAL:", duplicate_success)
    print("DUPLICATE MESSAGE:", duplicate_message)

    # Do NOT save test data
    conn.rollback()

    print()
    print("TEST CLEANUP: ROLLED BACK")
    print("No test data was saved.")

except Exception as e:

    conn.rollback()

    print()
    print("TEST FAILED:", e)
    print("TEST DATA WAS ROLLED BACK.")

finally:

    conn.close()