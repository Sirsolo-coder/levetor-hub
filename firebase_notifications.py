import json

import firebase_admin
from firebase_admin import messaging
from firebase_admin import exceptions as firebase_exceptions


def _get_firebase_app():
    """
    Get the existing Firebase Admin app or initialize it
    using GOOGLE_APPLICATION_CREDENTIALS.
    """

    try:
        return firebase_admin.get_app()

    except ValueError:
        return firebase_admin.initialize_app()


def send_push_notification(
    fcm_token: str,
    title: str,
    body: str,
    data: dict | None = None,
) -> str:
    """
    Send one notification to one FCM registration token.
    """

    token = str(
        fcm_token or ""
    ).strip()

    if not token:
        raise ValueError(
            "FCM token is required."
        )

    clean_data = {}

    if data:

        for key, value in data.items():

            clean_data[str(key)] = str(
                value
            )

    message = messaging.Message(
        notification=messaging.Notification(
            title=str(title),
            body=str(body),
        ),
        data=clean_data,
        token=token,
    )

    app = _get_firebase_app()

    return messaging.send(
        message,
        app=app,
    )


def save_notification(
    conn,
    customer_id: int,
    title: str,
    body: str,
    data: dict | None = None,
):
    """
    Save a successfully generated notification to the
    notification history table.
    """

    clean_data = {}

    if data:

        for key, value in data.items():

            clean_data[str(key)] = str(
                value
            )

    notification_type = (
        clean_data.get(
            "type",
            "general"
        )
    )

    conn.execute(
        """
        INSERT INTO notifications
        (
            customer_id,
            title,
            body,
            notification_type,
            data,
            is_read
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            customer_id,
            str(title),
            str(body),
            notification_type,
            json.dumps(
                clean_data
            ),
            0,
        ),
    )

    conn.commit()


def send_customer_notification(
    conn,
    customer_id: int,
    title: str,
    body: str,
    data: dict | None = None,
) -> dict:
    """
    Look up a customer's FCM token, send the notification,
    and save it to notification history when successful.
    """

    customer = conn.execute(
        """
        SELECT
            id,
            fcm_token
        FROM customers
        WHERE id = ?
        """,
        (
            customer_id,
        ),
    ).fetchone()

    if customer is None:

        return {
            "success": False,
            "sent": False,
            "message": "Customer not found.",
        }

    token = str(
        customer["fcm_token"] or ""
    ).strip()

    if not token:

        return {
            "success": False,
            "sent": False,
            "message": (
                "Customer has no registered "
                "FCM token."
            ),
        }

    try:

        message_id = send_push_notification(
            fcm_token=token,
            title=title,
            body=body,
            data=data,
        )

        # Save notification history after
        # Firebase accepted the message.
        save_notification(
            conn=conn,
            customer_id=customer_id,
            title=title,
            body=body,
            data=data,
        )

        return {
            "success": True,
            "sent": True,
            "message": (
                "Notification sent successfully."
            ),
            "message_id": message_id,
        }

    except messaging.UnregisteredError:

        conn.execute(
            """
            UPDATE customers
            SET fcm_token = NULL
            WHERE id = ?
            """,
            (
                customer_id,
            ),
        )

        conn.commit()

        return {
            "success": False,
            "sent": False,
            "message": (
                "The customer's Firebase device "
                "token is no longer valid."
            ),
        }

    except firebase_exceptions.FirebaseError as e:

        return {
            "success": False,
            "sent": False,
            "message": (
                f"Firebase notification failed: {str(e)}"
            ),
        }

    except Exception as e:

        return {
            "success": False,
            "sent": False,
            "message": (
                f"Notification failed: {str(e)}"
            ),
        }