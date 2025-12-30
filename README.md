# ecom-microservices-project
Microservices-based E-Commerce Application with FastAPI, SQLModel, Docker, and Kubernetes

## Stripe payment (dev)

This project includes a minimal Stripe integration inside `payment-service`:

- `POST /payments/stripe/pay-url` (Bearer token) creates a PaymentIntent for the authenticated user's active checkout (no `order_id` required) and returns a ready-to-open hosted payment page URL.
- `GET /payments/stripe/pay?client_secret=...` is a simple hosted payment page using Stripe Payment Element.
- `POST /payments/stripe/webhook` receives Stripe webhooks and publishes `payment.succeeded` / `payment.failed` events via RabbitMQ so the Order/Product/Notification services can react.

### Required env vars (docker-compose)

Set the following (test) variables before running compose:

- `STRIPE_SECRET_KEY`
- `STRIPE_PUBLISHABLE_KEY`
- `STRIPE_WEBHOOK_SECRET`
- Optional: `PAYMENT_PUBLIC_URL` (default: `http://localhost:8003`)

### Local webhook forwarding

For local development you can use Stripe CLI to forward webhooks to:

`http://localhost:8003/payments/stripe/webhook`
