from __future__ import annotations

from typing import Any, Dict

from .emailer import pick_recipient, send_email


def handle_payment_event(payload: Dict[str, Any]) -> None:
    event = payload.get("event") or ""
    order_id = payload.get("order_id")
    user_id = payload.get("user_id")
    user_email = payload.get("user_email") or payload.get("email")

    to_email = pick_recipient(user_email)

    if event == "payment.succeeded":
        subject = f"Payment succeeded (order #{order_id})"
        status_line = "Payment status: SUCCESS"
    elif event == "payment.failed":
        subject = f"Payment failed (order #{order_id})"
        status_line = "Payment status: FAILED"
    else:
        # Unknown event; ignore to avoid spamming
        return

    body = "\n".join(
        [
            "This is a test notification from notification-service.",
            "",
            status_line,
            f"Order ID: {order_id}",
            f"User ID: {user_id}",
            f"Amount: {payload.get('amount')}",
            f"Payment ID: {payload.get('payment_id')}",
            f"Occurred At: {payload.get('occurred_at')}",
            "",
            "If you received this email, the RabbitMQ notification flow is working.",
        ]
    )

    send_email(to_email=to_email, subject=subject, body=body)
