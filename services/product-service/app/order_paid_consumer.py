from __future__ import annotations

import datetime as dt
from typing import Dict, Any, List

from .database import SessionLocal
from .crud import commit_reservations_and_decrease_stock
from .messaging import publish_event, start_consumer_in_thread


ORDER_PAID_QUEUE = "product-service.order.paid.q"


def _handle_order_paid(payload: Dict[str, Any]) -> None:
    """Expected payload (from order-service):
    {
      "order_id": 123,
      "items": [{"product_id": 1, "quantity": 2}, ...]
    }
    """
    order_id = payload.get("order_id")
    items: List[Dict[str, Any]] = payload.get("items") or []
    if not order_id or not items:
        return

    db = SessionLocal()
    try:
        # Decrement stock and clear any active reservations for this order
        commit_reservations_and_decrease_stock(db, order_id=int(order_id), items=items)

        # Emit: stock.decremented (optional)
        publish_event(
            "stock.decremented",
            {
                "event": "stock.decremented",
                "occurred_at": dt.datetime.utcnow().isoformat() + "Z",
                "order_id": int(order_id),
                "items": [{"product_id": int(i["product_id"]), "quantity": int(i["quantity"])} for i in items],
            },
        )
    finally:
        db.close()


def start_order_paid_consumer() -> None:
    start_consumer_in_thread(
        queue_name=ORDER_PAID_QUEUE,
        binding_keys=["order.paid"],
        handler=_handle_order_paid,
    )
