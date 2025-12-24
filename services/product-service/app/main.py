from fastapi import FastAPI
from .routers import product_router
from .models import Base
from .database import engine
from .order_paid_consumer import start_order_paid_consumer

app = FastAPI(title="Product Service")

Base.metadata.create_all(bind=engine)

app.include_router(product_router.router)


@app.on_event("startup")
def _startup() -> None:
    # Start background consumer for order.paid
    start_order_paid_consumer()