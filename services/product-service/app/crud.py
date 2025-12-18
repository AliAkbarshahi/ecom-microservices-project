from sqlalchemy.orm import Session
from sqlalchemy import or_
from .models import Product

def create_product(db: Session, product_data: dict):
    db_product = Product(**product_data)
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

def get_product(db: Session, product_id: int):
    return db.query(Product).filter(Product.id == product_id).first()

def get_products(db: Session, skip: int = 0, limit: int = 100, search: str = None):
    query = db.query(Product)
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                Product.name.ilike(search_pattern),
                Product.description.ilike(search_pattern),
                Product.category.ilike(search_pattern)
            )
        )
    return query.offset(skip).limit(limit).all()

def update_product(db: Session, product_id: int, update_data: dict):
    db_product = get_product(db, product_id)
    if not db_product:
        return None
    for key, value in update_data.items():
        if value is not None:
            setattr(db_product, key, value)
    db.commit()
    db.refresh(db_product)
    return db_product

def delete_product(db: Session, product_id: int):
    db_product = get_product(db, product_id)
    if db_product:
        db.delete(db_product)
        db.commit()
    return db_product