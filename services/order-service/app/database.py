from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/order_db")

engine = create_engine(DATABASE_URL)    # Connecting to the database
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)   #A temporary connection to work with the database.

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()  