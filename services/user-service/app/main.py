from fastapi import FastAPI
from .database import Base, engine, SessionLocal
from .routers import user_router, admin_router
from .crud import get_user_by_username
from .auth import get_password_hash
from .models import User
from .migrations import add_is_admin_column

app = FastAPI(title="User Service")

Base.metadata.create_all(bind=engine)  

app.include_router(user_router.router)
app.include_router(admin_router.router)


def init_admin_user():
   
    db = SessionLocal()
    try:
        admin_user = get_user_by_username(db, username="admin")
        if not admin_user:
            hashed_password = get_password_hash("admin")
            # Create admin user with is_admin=True
            admin_user = User(
                username="admin",
                email="admin@admin.com",
                hashed_password=hashed_password,
                is_admin=True
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
            print("Admin user created successfully!")
        else:
            # Ensure admin user has is_admin=True
            if not admin_user.is_admin:
                admin_user.is_admin = True
                db.commit()
                print("Admin user updated successfully!")
    except Exception as e:
        print(f"Error initializing admin user: {e}")
        db.rollback()
    finally:
        db.close()


@app.on_event("startup")
async def startup_event():
    # Run migration to add is_admin column
    add_is_admin_column()
    # Initialize admin user
    init_admin_user()


@app.get("/")
def health_check():
    return {"status": "User Service is running!"}