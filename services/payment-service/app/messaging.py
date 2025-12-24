from __future__ import annotations

import json
import os

import pika

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://admin:admin123@rabbitmq:5672/")
EVENTS_EXCHANGE = os.getenv("EVENTS_EXCHANGE", "ecom.events")


def _connect() -> pika.BlockingConnection:
    params = pika.URLParameters(RABBITMQ_URL)
    params.heartbeat = 30
    params.blocked_connection_timeout = 30
    return pika.BlockingConnection(params)


def publish_event(routing_key: str, payload: dict) -> None:
    connection = _connect()
    try:
        ch = connection.channel()
        ch.exchange_declare(exchange=EVENTS_EXCHANGE, exchange_type="topic", durable=True)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        ch.basic_publish(
            exchange=EVENTS_EXCHANGE,
            routing_key=routing_key,
            body=body,
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,
            ),
        )
    finally:
        connection.close()
