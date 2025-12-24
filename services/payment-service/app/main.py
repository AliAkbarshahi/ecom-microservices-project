from __future__ import annotations

import datetime as dt

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .messaging import publish_event


app = FastAPI(title="Payment Service", version="0.1.0")


class PaymentSucceedRequest(BaseModel):
    amount: float | None = Field(None, ge=0)
    payment_id: str | None = None


@app.post("/payments/{order_id}/succeed")
def succeed_payment(order_id: int, body: PaymentSucceedRequest | None = None):
    payload = {
        "event": "payment.succeeded",
        "occurred_at": dt.datetime.utcnow().isoformat() + "Z",
        "order_id": order_id,
        "amount": body.amount if body else None,
        "payment_id": body.payment_id if body else None,
    }
    publish_event("payment.succeeded", payload)
    return {"status": "published", "event": payload}


@app.get("/")
def root():
    return {"service": "payment-service", "status": "running"}
