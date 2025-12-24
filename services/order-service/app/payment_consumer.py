from __future__ import annotations

import datetime as dt
from typing import Dict, Any

from .database import SessionLocal
from . import crud
from .messaging import publish_event, start_consumer_in_thread


PAYMENT_SUCCEEDED_QUEUE = "order-service.payment.succeeded.q"


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
        order = crud.mark_order_paid(db, int(order_id))
        if not order:
            return

        # Build order.paid payload with only what Product Service needs
        event_payload = {
            "event": "order.paid",
            "occurred_at": dt.datetime.utcnow().isoformat() + "Z",
            "order_id": order.id,
            "user_id": order.user_id,
            "items": [
                {"product_id": i.product_id, "quantity": i.quantity}
                for i in order.items
            ],
        }
        publish_event("order.paid", event_payload)
    finally:
        db.close()


def start_payment_succeeded_consumer() -> None:
    start_consumer_in_thread(
        queue_name=PAYMENT_SUCCEEDED_QUEUE,
        binding_keys=["payment.succeeded"],
        handler=_handle_payment_succeeded,
    )
