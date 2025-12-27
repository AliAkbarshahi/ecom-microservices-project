from __future__ import annotations

import datetime as dt
import os
import requests

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field

from .messaging import publish_event
from .auth import get_current_user


ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://order-service:8000")


app = FastAPI(title="Payment Service", version="0.1.0")


class PaymentSucceedRequest(BaseModel):
    amount: float | None = Field(None, ge=0)
    payment_id: str | None = None


# @app.post("/payments/{order_id}/succeed")
# def succeed_payment(order_id: int, body: PaymentSucceedRequest | None = None):
#     payload = {
#         "event": "payment.succeeded",
#         "occurred_at": dt.datetime.utcnow().isoformat() + "Z",
#         "order_id": order_id,
#         "amount": body.amount if body else None,
#         "payment_id": body.payment_id if body else None,
#     }
#     publish_event("payment.succeeded", payload)
#     return {"status": "published", "event": payload}


def _get_checkout_order_id_for_user(token: str) -> dict:
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(f"{ORDER_SERVICE_URL}/orders/checkout", headers=headers, timeout=5)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="No active checkout found for this user")
        raise HTTPException(status_code=500, detail=f"Failed to get checkout order: {resp.text}")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=503, detail=f"Order service is unavailable: {str(e)}")


@app.post("/payments/succeed")
def succeed_payment_me(
   # body: PaymentSucceedRequest | None = None,
    current_user: dict = Depends(get_current_user),
):
    """Publish payment.succeeded for the authenticated user's active checkout.

    No order_id is required; we infer it from the user's token.
    """

    checkout = _get_checkout_order_id_for_user(current_user["token"])
    order_id = int(checkout["order_id"])

    payload = {
        "event": "payment.succeeded",
        "occurred_at": dt.datetime.utcnow().isoformat() + "Z",
        "order_id": order_id,
        "amount": (body.amount if (body and body.amount is not None) else checkout.get("total_amount")),
        "payment_id": body.payment_id if body else None,
    }
    publish_event("payment.succeeded", payload)
    return {"status": "published", "event": payload}


@app.post("/payments/fail")
def fail_payment_me(
    current_user: dict = Depends(get_current_user),
):
    """Publish payment.failed for the authenticated user's active checkout.

    No order_id is required.
    """
    checkout = _get_checkout_order_id_for_user(current_user["token"])
    order_id = int(checkout["order_id"])
    payload = {
        "event": "payment.failed",
        "occurred_at": dt.datetime.utcnow().isoformat() + "Z",
        "order_id": order_id,
    }
    publish_event("payment.failed", payload)
    return {"status": "published", "event": payload}


@app.get("/")
def root():
    return {"service": "payment-service", "status": "running"}
