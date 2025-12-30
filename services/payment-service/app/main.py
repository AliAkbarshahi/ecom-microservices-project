from __future__ import annotations

import datetime as dt
from decimal import Decimal, ROUND_HALF_UP
import os
from urllib.parse import quote_plus
import requests

import stripe

from fastapi import FastAPI, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .messaging import publish_event
from .auth import get_current_user


ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://order-service:8000")


STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_CURRENCY = os.getenv("STRIPE_CURRENCY", "usd")

# Used only to build an absolute URL that you can open in a browser.
# In local docker-compose, this should be: http://localhost:8003
PAYMENT_PUBLIC_URL = os.getenv("PAYMENT_PUBLIC_URL", "http://localhost:8003")


app = FastAPI(title="Payment Service", version="0.1.0")


def _stripe_required() -> None:
    if not STRIPE_SECRET_KEY or not STRIPE_PUBLISHABLE_KEY:
        raise HTTPException(
            status_code=500,
            detail="Stripe is not configured. Set STRIPE_SECRET_KEY and STRIPE_PUBLISHABLE_KEY.",
        )
    stripe.api_key = STRIPE_SECRET_KEY


def _parse_reserved_until(reserved_until: str | None) -> dt.datetime | None:
    if not reserved_until:
        return None
    # Order service returns RFC3339 like: 2025-12-29T12:00:00Z
    s = reserved_until.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _to_minor_units(amount: float) -> int:
    # Convert decimal currency to integer minor units (e.g., cents)
    dec = Decimal(str(amount))
    minor = (dec * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(minor)


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


# @app.post("/payments/succeed")
# def succeed_payment_me(
#     body: PaymentSucceedRequest | None = None,
#     current_user: dict = Depends(get_current_user),
# ):
#     """Publish payment.succeeded for the authenticated user's active checkout.

#     No order_id is required; we infer it from the user's token.
#     """

#     checkout = _get_checkout_order_id_for_user(current_user["token"])
#     order_id = int(checkout["order_id"])

#     payload = {
#         "event": "payment.succeeded",
#         "occurred_at": dt.datetime.utcnow().isoformat() + "Z",
#         "order_id": order_id,
#         "user_id": current_user.get("id"),
#         "user_email": current_user.get("email"),
#         "amount": (body.amount if (body and body.amount is not None) else checkout.get("total_amount")),
#         "payment_id": body.payment_id if body else None,
#     }
#     publish_event("payment.succeeded", payload)
#     return {"status": "published", "event": payload}


# @app.post("/payments/fail")
# def fail_payment_me(
#     current_user: dict = Depends(get_current_user),
# ):
#     """Publish payment.failed for the authenticated user's active checkout.

#     No order_id is required.
#     """
#     checkout = _get_checkout_order_id_for_user(current_user["token"])
#     order_id = int(checkout["order_id"])
#     payload = {
#         "event": "payment.failed",
#         "occurred_at": dt.datetime.utcnow().isoformat() + "Z",
#         "order_id": order_id,
#         "user_id": current_user.get("id"),
#         "user_email": current_user.get("email"),
#     }
#     publish_event("payment.failed", payload)
#     return {"status": "published", "event": payload}


class StripeIntentResponse(BaseModel):
    payment_intent_id: str
    client_secret: str
    payment_url: str
    reserved_until: str | None = None


@app.post("/payments/stripe/pay-url", response_model=StripeIntentResponse)
def create_stripe_payment_for_checkout(
    current_user: dict = Depends(get_current_user),
):
    """Create a Stripe PaymentIntent for the authenticated user's active checkout.

    Returns a ready-to-open hosted payment page (served by this service) that will
    confirm the payment and redirect back to /payments/stripe/return.

    NOTE: This endpoint does not take order_id; it infers the active checkout from the token.
    """
    _stripe_required()

    checkout = _get_checkout_order_id_for_user(current_user["token"])
    order_id = int(checkout["order_id"])
    reserved_until = _parse_reserved_until(checkout.get("reserved_until"))

    if reserved_until is not None:
        now = dt.datetime.now(dt.timezone.utc)
        if now >= reserved_until:
            raise HTTPException(status_code=409, detail="Checkout expired. Please checkout again.")

    total_amount = float(checkout.get("total_amount") or 0)
    if total_amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid order amount")

    amount_minor = _to_minor_units(total_amount)

    intent = stripe.PaymentIntent.create(
        amount=amount_minor,
        currency=STRIPE_CURRENCY,
        automatic_payment_methods={"enabled": True},
        metadata={
            "order_id": str(order_id),
            "user_id": str(current_user.get("id") or ""),
            "user_email": str(current_user.get("email") or ""),
        },
        description=f"Order #{order_id}",
    )

    # client_secret is safe to send to the client; it is required by Stripe.js
    reserved_until_str = checkout.get("reserved_until")
    payment_url = f"{PAYMENT_PUBLIC_URL}/payments/stripe/pay?client_secret={quote_plus(intent.client_secret)}"
    if reserved_until_str:
        payment_url += f"&reserved_until={quote_plus(str(reserved_until_str))}"
    return {
        "payment_intent_id": intent.id,
        "client_secret": intent.client_secret,
        "payment_url": payment_url,
        "reserved_until": reserved_until_str,
    }


@app.get("/payments/stripe/pay", response_class=HTMLResponse,include_in_schema=False)
def stripe_payment_page(
    client_secret: str = Query(..., description="Stripe PaymentIntent client_secret"),
    reserved_until: str | None = Query(None, description="Reservation expires at (RFC3339), for countdown UI"),
):
    """Simple hosted payment page (for demo/dev) using Stripe Payment Element.

    In production, you typically serve your own frontend; this page is intentionally minimal.
    """
    _stripe_required()

    if not client_secret.startswith("pi_"):
        # Not a strict guarantee, but prevents obvious misuse.
        raise HTTPException(status_code=400, detail="Invalid client_secret")

    if not STRIPE_PUBLISHABLE_KEY:
        raise HTTPException(status_code=500, detail="Stripe publishable key is missing")

    html = f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Stripe Payment</title>
    <script src=\"https://js.stripe.com/v3/\"></script>
    <style>
      body {{ font-family: Arial, sans-serif; max-width: 720px; margin: 40px auto; padding: 0 16px; }}
      .card {{ border: 1px solid #ddd; border-radius: 12px; padding: 20px; }}
      button {{ width: 100%; padding: 12px; font-size: 16px; cursor: pointer; }}
      #message {{ margin-top: 12px; color: #b00020; }}
      .muted {{ color: #666; font-size: 13px; }}
    </style>
  </head>
  <body>
    <h2>پرداخت سفارش</h2>
    <div class=\"card\">
      <div id=\"timer\" class=\"muted\"></div>
      <div style=\"height: 10px\"></div>
      <form id=\"payment-form\">
        <div id=\"payment-element\"></div>
        <div style=\"height: 16px\"></div>
        <button id=\"submit\" type=\"submit\">Pay</button>
        <div id=\"message\"></div>
        <p class=\"muted\">پس از پرداخت، به همین سرویس برمی‌گردید و سپس وضعیت سفارش در Order Service به‌روزرسانی می‌شود (از طریق Webhook).</p>
      </form>
    </div>

    <script>
      const clientSecret = {client_secret!r};
      const reservedUntil = {reserved_until!r};
      const stripe = Stripe({STRIPE_PUBLISHABLE_KEY!r});
      const elements = stripe.elements({{ clientSecret }});
      const paymentElement = elements.create('payment');
      paymentElement.mount('#payment-element');

      const form = document.getElementById('payment-form');
      const message = document.getElementById('message');
      const submitBtn = document.getElementById('submit');
      const timerEl = document.getElementById('timer');

      function startCountdown() {{
        if (!reservedUntil) return;
        const exp = Date.parse(reservedUntil);
        if (!Number.isFinite(exp)) return;
        const tick = () => {{
          const ms = exp - Date.now();
          const s = Math.floor(ms / 1000);
          if (s <= 0) {{
            timerEl.textContent = 'مهلت رزرو به پایان رسیده. لطفاً Checkout را دوباره انجام دهید.';
            timerEl.style.color = '#b00020';
            submitBtn.disabled = true;
            return;
          }}
          timerEl.textContent = 'مهلت پرداخت (رزرو موجودی): ' + s + ' ثانیه';
          setTimeout(tick, 500);
        }};
        tick();
      }}
      startCountdown();

      function setLoading(isLoading) {{
        submitBtn.disabled = isLoading;
        submitBtn.textContent = isLoading ? 'Processing…' : 'Pay';
      }}

      form.addEventListener('submit', async (e) => {{
        e.preventDefault();
        setLoading(true);
        message.textContent = '';

        const {{ error }} = await stripe.confirmPayment({{
          elements,
          confirmParams: {{
            return_url: window.location.origin + '/payments/stripe/return'
          }}
        }});

        if (error) {{
          message.textContent = error.message || 'Payment failed.';
          setLoading(false);
        }}
      }});
    </script>
  </body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/payments/stripe/return", response_class=HTMLResponse,include_in_schema=False)
def stripe_return_page():
    """Return page after Stripe redirects back.

    Stripe appends payment_intent_client_secret to the query string.
    We use Stripe.js to fetch and display the status.
    """
    _stripe_required()

    html = f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Payment Result</title>
    <script src=\"https://js.stripe.com/v3/\"></script>
    <style>
      body {{ font-family: Arial, sans-serif; max-width: 720px; margin: 40px auto; padding: 0 16px; }}
      .card {{ border: 1px solid #ddd; border-radius: 12px; padding: 20px; }}
      .ok {{ color: #0a7; }}
      .bad {{ color: #b00; }}
      .muted {{ color: #666; font-size: 13px; }}
      a {{ word-break: break-all; }}
    </style>
  </head>
  <body>
    <h2>نتیجه پرداخت</h2>
    <div class=\"card\">
      <div id=\"status\" class=\"muted\">در حال دریافت وضعیت…</div>
      <div id=\"details\" class=\"muted\"></div>
      <hr />
      <p class=\"muted\">
        نکته: به‌روزرسانی وضعیت سفارش در Order Service از طریق Webhook انجام می‌شود و ممکن است چند ثانیه زمان ببرد.
      </p>
      <p>
        برای مشاهده وضعیت سفارش: <a href=\"http://localhost:8002/docs\" target=\"_blank\">Order Service Swagger</a>
      </p>
    </div>

    <script>
      const stripe = Stripe({STRIPE_PUBLISHABLE_KEY!r});
      const params = new URLSearchParams(window.location.search);
      const clientSecret = params.get('payment_intent_client_secret') || params.get('client_secret');

      const statusEl = document.getElementById('status');
      const detailsEl = document.getElementById('details');

      async function run() {{
        if (!clientSecret) {{
          statusEl.textContent = 'Missing payment_intent_client_secret.';
          statusEl.className = 'bad';
          return;
        }}
        const result = await stripe.retrievePaymentIntent(clientSecret);
        if (result.error) {{
          statusEl.textContent = result.error.message || 'Failed to retrieve payment.';
          statusEl.className = 'bad';
          return;
        }}
        const pi = result.paymentIntent;
        const st = pi.status;
        detailsEl.textContent = 'PaymentIntent: ' + pi.id;
        if (st === 'succeeded') {{
          statusEl.textContent = 'پرداخت موفق بود.';
          statusEl.className = 'ok';
        }} else if (st === 'processing') {{
          statusEl.textContent = 'پرداخت در حال پردازش است.';
          statusEl.className = 'muted';
        }} else if (st === 'requires_payment_method') {{
          statusEl.textContent = 'پرداخت ناموفق بود یا لغو شد. دوباره تلاش کنید.';
          statusEl.className = 'bad';
        }} else {{
          statusEl.textContent = 'وضعیت پرداخت: ' + st;
          statusEl.className = 'muted';
        }}
      }}
      run();
    </script>
  </body>
</html>"""
    return HTMLResponse(content=html)


@app.post("/payments/stripe/webhook",include_in_schema=False)
async def stripe_webhook(request: Request):
    """Stripe webhook endpoint.

    Configure this URL in Stripe (or via stripe-cli) and set STRIPE_WEBHOOK_SECRET.
    """
    _stripe_required()
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="STRIPE_WEBHOOK_SECRET is not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=STRIPE_WEBHOOK_SECRET,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook signature verification failed: {str(e)}")

    event_type = event.get("type")
    data_object = (event.get("data") or {}).get("object") or {}

    if event_type == "payment_intent.succeeded":
        metadata = data_object.get("metadata") or {}
        order_id = metadata.get("order_id")
        user_id = metadata.get("user_id")
        user_email = metadata.get("user_email")
        if order_id:
            amount_received = data_object.get("amount_received")
            payload_out = {
                "event": "payment.succeeded",
                "occurred_at": dt.datetime.utcnow().isoformat() + "Z",
                "order_id": int(order_id),
                "user_id": int(user_id) if str(user_id).isdigit() else None,
                "user_email": user_email or None,
                "amount": (amount_received / 100.0) if isinstance(amount_received, int) else None,
                "payment_id": data_object.get("id"),
                "provider": "stripe",
            }
            publish_event("payment.succeeded", payload_out)

    elif event_type == "payment_intent.payment_failed":
        metadata = data_object.get("metadata") or {}
        order_id = metadata.get("order_id")
        user_id = metadata.get("user_id")
        user_email = metadata.get("user_email")
        if order_id:
            last_err = data_object.get("last_payment_error") or {}
            payload_out = {
                "event": "payment.failed",
                "occurred_at": dt.datetime.utcnow().isoformat() + "Z",
                "order_id": int(order_id),
                "user_id": int(user_id) if str(user_id).isdigit() else None,
                "user_email": user_email or None,
                "payment_id": data_object.get("id"),
                "provider": "stripe",
                "reason": last_err.get("message"),
            }
            publish_event("payment.failed", payload_out)

    # Always return 200 to acknowledge receipt.
    return {"received": True}


@app.get("/")
def root():
    return {"service": "payment-service", "status": "running"}
