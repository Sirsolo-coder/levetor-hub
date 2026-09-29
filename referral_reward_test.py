from database import get_db
from app import (
    ensure_customer_referral_code,
    create_referral,
    process_referral_qualification
)


conn = get_db()

try:
    conn.execute("BEGIN")

    # =====================================================
    # CREATE TEST REFERRER
    # =====================================================

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
        "Reward Test Referrer",
        "reward_referrer_test@levetor.local",
        "08000000011",
        "Test Address",
        "test-password-hash"
    ))

    referrer_id = referrer_cursor.lastrowid

    referral_code = ensure_customer_referral_code(
        conn,
        referrer_id
    )

    # =====================================================
    # CREATE TEST REFEREE
    # =====================================================

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
        "Reward Test Referee",
        "reward_referee_test@levetor.local",
        "08000000012",
        "Test Address",
        "test-password-hash"
    ))

    referee_id = referee_cursor.lastrowid

    # =====================================================
    # CREATE REFERRAL
    # =====================================================

    success, message = create_referral(
        conn,
        referrer_id,
        referee_id,
        referral_code
    )

    print("REFERRAL CREATED:", success)
    print("MESSAGE:", message)

    # =====================================================
    # CREATE TEST ORDER
    # =====================================================

    order_cursor = conn.execute("""
        INSERT INTO orders
        (
            customer_id,
            total_amount,
            payment_status,
            order_status
        )
        VALUES (?, ?, ?, ?)
    """, (
        referee_id,
        50000.0,
        "Paid",
        "Processing"
    ))

    order_id = order_cursor.lastrowid

    print("TEST ORDER ID:", order_id)

    # =====================================================
    # PROCESS REFERRAL REWARD
    # =====================================================

    reward_processed = process_referral_qualification(
        conn,
        referee_id,
        order_id,
        50000.0
    )

    print(
        "REWARD PROCESSED:",
        reward_processed
    )

    # =====================================================
    # CHECK REFERRAL STATUS
    # =====================================================

    referral = conn.execute("""
        SELECT
            id,
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

    print(
        "REFERRAL AFTER REWARD:",
        dict(referral)
    )

    # =====================================================
    # CHECK BOTH STORE CREDIT BALANCES
    # =====================================================

    balances = conn.execute("""
        SELECT
            id,
            fullname,
            store_credit_balance
        FROM customers
        WHERE id IN (?, ?)
        ORDER BY id
    """, (
        referrer_id,
        referee_id
    )).fetchall()

    print("STORE CREDIT BALANCES:")

    for customer in balances:
        print(
            dict(customer)
        )

    # =====================================================
    # CHECK CREDIT TRANSACTIONS
    # =====================================================

    transactions = conn.execute("""
        SELECT
            customer_id,
            amount,
            transaction_type,
            reference_type,
            reference_id,
            description
        FROM store_credit_transactions
        WHERE reference_type = 'referral'
        AND reference_id = ?
        ORDER BY customer_id
    """, (
        referral["id"],
    )).fetchall()

    print("CREDIT TRANSACTIONS:")

    for transaction in transactions:
        print(
            dict(transaction)
        )

    # =====================================================
    # TEST DUPLICATE REWARD PROTECTION
    # =====================================================

    second_attempt = process_referral_qualification(
        conn,
        referee_id,
        order_id,
        50000.0
    )

    print(
        "SECOND REWARD ATTEMPT:",
        second_attempt
    )

    # =====================================================
    # VERIFY FINAL BALANCES
    # =====================================================

    final_balances = conn.execute("""
        SELECT
            id,
            fullname,
            store_credit_balance
        FROM customers
        WHERE id IN (?, ?)
        ORDER BY id
    """, (
        referrer_id,
        referee_id
    )).fetchall()

    print("FINAL STORE CREDIT BALANCES:")

    for customer in final_balances:
        print(
            dict(customer)
        )

    # =====================================================
    # ROLLBACK TEST DATA
    # =====================================================

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