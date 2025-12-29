from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
from typing import Callable, Iterable

import pika

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://admin:admin123@rabbitmq:5672/")
EVENTS_EXCHANGE = os.getenv("EVENTS_EXCHANGE", "ecom.events")


def _connect() -> pika.BlockingConnection:
    params = pika.URLParameters(RABBITMQ_URL)
    params.heartbeat = 30
    params.blocked_connection_timeout = 30
    return pika.BlockingConnection(params)


def start_consumer_in_thread(
    *,
    queue_name: str,
    binding_keys: Iterable[str],
    handler: Callable[[dict], None],
    prefetch_count: int = 10,
    daemon: bool = True,
) -> None:
    def _run() -> None:
        while True:
            connection = None
            try:
                connection = _connect()
                ch = connection.channel()
                ch.exchange_declare(exchange=EVENTS_EXCHANGE, exchange_type="topic", durable=True)

                ch.queue_declare(queue=queue_name, durable=True)
                for key in binding_keys:
                    ch.queue_bind(exchange=EVENTS_EXCHANGE, queue=queue_name, routing_key=key)

                ch.basic_qos(prefetch_count=prefetch_count)

                def _on_message(ch_, method, properties, body: bytes):
                    try:
                        payload = json.loads(body.decode("utf-8"))
                        handler(payload)
                        ch_.basic_ack(delivery_tag=method.delivery_tag)
                    except Exception:
                        try:
                            print(
                                f"[notification-service] consumer handler failed. queue={queue_name}",
                                file=sys.stderr,
                            )
                            traceback.print_exc()
                        except Exception:
                            pass
                        ch_.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

                ch.basic_consume(queue=queue_name, on_message_callback=_on_message, auto_ack=False)
                ch.start_consuming()
            except Exception:
                time.sleep(3)
            finally:
                try:
                    if connection:
                        connection.close()
                except Exception:
                    pass

    t = threading.Thread(target=_run, name=f"consumer:{queue_name}", daemon=daemon)
    t.start()
