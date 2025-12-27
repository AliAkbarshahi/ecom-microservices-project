from __future__ import annotations

import datetime as dt
from typing import Dict, Any

from .database import SessionLocal
from . import crud
from .messaging import publish_event, start_consumer_in_thread


PAYMENT_SUCCEEDED_QUEUE = "order-service.payment.succeeded.q"
PAYMENT_FAILED_QUEUE = "order-service.payment.failed.q"


def _handle_payment_succeeded(payload: Dict[str, Any]) -> None:
    """Expected payload:
    {
      "order_id": 123,
      "payment_id": "..." (optional),
      "amount": 999.0 (optional)
    }
    """
    order_id = payload.get("order_id")
    if not order_id:
        # nothing we can do
        return

    db = SessionLocal()
    try:
        # Validate: must be within reservation window
        order = crud.get_order(db, int(order_id))
        if not order:
            return

        # IMPORTANT:
        # SQLAlchemy may hydrate timestamptz as timezone-aware values, while
        # datetime.utcnow() is timezone-naive. Comparing aware vs naive raises
        # TypeError and would cause the consumer to drop the message.
        now = dt.datetime.now(dt.timezone.utc)
        exp = order.checkout_expires_at
        if exp is not None:
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=dt.timezone.utc)
            else:
                exp = exp.astimezone(dt.timezone.utc)
        if (
            order.payment_status
            or order.status != "checkout_pending"
            or not exp
            or exp <= now
        ):
            # Treat as expired/invalid checkout: cancel but keep items, release reservation best-effort
            order.payment_status = False
            order.status = "cancelled"
            order.checkout_expires_at = None
            db.commit()
            try:
                from .external_services import release_stock_reservation

                release_stock_reservation(order_id=int(order_id))
            except Exception:
                pass
            return

        # Mark paid and emit order.paid event for stock decrement
        order = crud.mark_order_paid(db, int(order_id))
        if not order:
            return

        event_payload = {
            "event": "order.paid",
            "occurred_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            "order_id": order.id,
            "user_id": order.user_id,
            "items": [{"product_id": i.product_id, "quantity": i.quantity} for i in order.items],
        }
        publish_event("order.paid", event_payload)
    finally:
        db.close()


def _handle_payment_failed(payload: Dict[str, Any]) -> None:
    """Cancel the checkout (keep cart items) and release reservations."""
    order_id = payload.get("order_id")
    if not order_id:
        return

    db = SessionLocal()
    try:
        order = crud.get_order(db, int(order_id))
        if not order:
            return
        if order.payment_status:
            return

        order.payment_status = False
        order.status = "cancelled"
        order.checkout_expires_at = None
        db.commit()

        try:
            from .external_services import release_stock_reservation

            release_stock_reservation(order_id=int(order_id))
        except Exception:
            pass
    finally:
        db.close()


def start_payment_succeeded_consumer() -> None:
    start_consumer_in_thread(
        queue_name=PAYMENT_SUCCEEDED_QUEUE,
        binding_keys=["payment.succeeded"],
        handler=_handle_payment_succeeded,
    )


def start_payment_failed_consumer() -> None:
    start_consumer_in_thread(
        queue_name=PAYMENT_FAILED_QUEUE,
        binding_keys=["payment.failed"],
        handler=_handle_payment_failed,
    )


def start_payment_consumers() -> None:
    start_payment_succeeded_consumer()
    start_payment_failed_consumer()
