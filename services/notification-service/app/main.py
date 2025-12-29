from __future__ import annotations

import os

from fastapi import FastAPI

from .messaging import start_consumer_in_thread
from .handlers import handle_payment_event

APP_NAME = "notification-service"

PAYMENT_QUEUE = os.getenv("NOTIFICATION_PAYMENT_QUEUE", "notification-service.payment.q")

app = FastAPI(title="Notification Service", version="0.1.0")


@app.on_event("startup")
def _startup() -> None:
    # listen to payment result events
    start_consumer_in_thread(
        queue_name=PAYMENT_QUEUE,
        binding_keys=["payment.succeeded", "payment.failed"],
        handler=handle_payment_event,
        prefetch_count=5,
    )


@app.get("/")
def root():
    return {"service": APP_NAME, "status": "running"}


@app.get("/health")
def health():
    return {"ok": True}
