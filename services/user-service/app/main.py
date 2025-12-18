from fastapi import FastAPI
from .database import Base, engine
from .routers import user_router

app = FastAPI(title="User Service")

Base.metadata.create_all(bind=engine)  

app.include_router(user_router.router)

@app.get("/")
def health_check():
    return {"status": "User Service is running!"}