from fastapi import FastAPI
from .routers import product_router
from .models import Base
from .database import engine

app = FastAPI(title="Product Service")

Base.metadata.create_all(bind=engine)

app.include_router(product_router.router)