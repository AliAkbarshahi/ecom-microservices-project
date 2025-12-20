
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import order_router
from .models import Base
from .database import engine

app = FastAPI(
    title="Order Service",
    description="Microservice for managing orders in e-commerce application",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create database tables
Base.metadata.create_all(bind=engine)

# Include routers
app.include_router(order_router.router)


@app.get("/")
def root():
   
    return {
        "service": "Order Service",
        "status": "running",
        "version": "1.0.0"
    }


@app.get("/health")
def health_check():
  
    return {
        "status": "healthy",
        "service": "order-service"
    }