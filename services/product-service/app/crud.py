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


def decrease_stock(db: Session, product_id: int, quantity: int) -> Product | None:
 
    if quantity <= 0:
        raise ValueError("quantity must be > 0")

    product = (
        db.query(Product)
        .filter(Product.id == product_id)
        .with_for_update()
        .first()
    )
    if not product:
        return None

    if product.stock < quantity:
        raise ValueError("insufficient_stock")

    product.stock -= quantity
    db.commit()
    db.refresh(product)
    return product


def decrease_stock_batch(db: Session, items: list[dict]) -> None:
    
    # Merge duplicate product_ids
    merged: dict[int, int] = {}
    for item in items:
        pid = int(item["product_id"])
        qty = int(item["quantity"])
        if qty <= 0:
            raise ValueError("quantity must be > 0")
        merged[pid] = merged.get(pid, 0) + qty

    try:
        # Lock rows in a stable order to avoid deadlocks
        for pid in sorted(merged.keys()):
            qty = merged[pid]
            product = (
                db.query(Product)
                .filter(Product.id == pid)
                .with_for_update()
                .first()
            )
            if not product:
                raise ValueError(f"product_not_found:{pid}")
            if product.stock < qty:
                raise ValueError(f"insufficient_stock:{pid}")
            product.stock -= qty

        db.commit()
    except Exception:
        db.rollback()
        raise