import datetime as dt
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from .models import Product, StockReservation

def get_product_by_name(db: Session, name: str):
    normalized = (name or "").strip()
    if not normalized:
        return None
    return (
        db.query(Product)
        .filter(func.lower(Product.name) == normalized.lower())
        .first()
    )

def create_product(db: Session, product_data: dict):
    # Enforce unique product name (case-insensitive)
    name = (product_data.get("name") or "").strip()
    if not name:
        raise ValueError("name_required")

    existing = (
        db.query(Product)
        .filter(func.lower(Product.name) == name.lower())
        .first()
    )
    if existing:
        raise ValueError("duplicate_product_name")

    db_product = Product(**{**product_data, "name": name})
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

    # Enforce unique name on rename (case-insensitive)
    if "name" in update_data and update_data.get("name") is not None:
        new_name = str(update_data["name"]).strip()
        if not new_name:
            raise ValueError("name_required")
        existing = (
            db.query(Product)
            .filter(func.lower(Product.name) == new_name.lower())
            .filter(Product.id != product_id)
            .first()
        )
        if existing:
            raise ValueError("duplicate_product_name")
        update_data["name"] = new_name

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


# -----------------------------
# Reservations (checkout hold)
# -----------------------------

def purge_expired_reservations(db: Session) -> int:
    """Delete expired reservations and return deleted rows count."""
    now = dt.datetime.now(dt.timezone.utc)
    q = db.query(StockReservation).filter(StockReservation.expires_at <= now)
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return int(deleted or 0)


def _reserved_qty_for_product(db: Session, product_id: int, *, now: dt.datetime, exclude_order_id: int | None = None) -> int:
    q = db.query(func.coalesce(func.sum(StockReservation.quantity), 0)).filter(
        StockReservation.product_id == product_id,
        StockReservation.expires_at > now,
    )
    if exclude_order_id is not None:
        q = q.filter(StockReservation.order_id != exclude_order_id)
    return int(q.scalar() or 0)


def create_reservations(
    db: Session,
    *,
    order_id: int,
    user_id: int,
    items: list[dict[str, Any]],
    ttl_seconds: int = 60,
) -> dt.datetime:
    """Reserve stock for an order for ttl_seconds.

    items: [{"product_id": int, "quantity": int}, ...]
    Returns: reserved_until (UTC datetime)
    """
    if ttl_seconds <= 0:
        ttl_seconds = 60

    now = dt.datetime.now(dt.timezone.utc)
    reserved_until = now + dt.timedelta(seconds=ttl_seconds)

    # Purge expired and clear any existing reservations for this order (retry checkout)
    db.query(StockReservation).filter(StockReservation.expires_at <= now).delete(synchronize_session=False)
    db.query(StockReservation).filter(StockReservation.order_id == order_id).delete(synchronize_session=False)
    db.flush()

    # Merge duplicates
    merged: dict[int, int] = {}
    for it in items:
        pid = int(it["product_id"])
        qty = int(it["quantity"])
        if qty <= 0:
            raise ValueError("quantity must be > 0")
        merged[pid] = merged.get(pid, 0) + qty

    try:
        # Lock products in stable order and validate availability
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

            reserved_qty = _reserved_qty_for_product(db, pid, now=now, exclude_order_id=order_id)
            available = int(product.stock) - int(reserved_qty)
            if available < qty:
                raise ValueError(f"insufficient_available_stock:{pid}:{available}:{qty}")

        # Create reservations
        for pid, qty in merged.items():
            db.add(
                StockReservation(
                    order_id=order_id,
                    user_id=user_id,
                    product_id=pid,
                    quantity=qty,
                    expires_at=reserved_until,
                )
            )

        db.commit()
        return reserved_until
    except Exception:
        db.rollback()
        raise


def release_reservations(db: Session, *, order_id: int) -> int:
    now = dt.datetime.now(dt.timezone.utc)
    # Purge expired too
    db.query(StockReservation).filter(StockReservation.expires_at <= now).delete(synchronize_session=False)
    q = db.query(StockReservation).filter(StockReservation.order_id == order_id)
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return int(deleted or 0)


def commit_reservations_and_decrease_stock(db: Session, *, order_id: int, items: list[dict[str, Any]]) -> None:
    """Decrease stock for items and remove reservations for this order.

    This is called when payment is successful.
    """
    # Decrease stock (locks product rows)
    decrease_stock_batch(db, items)

    # Remove reservations for the order (best-effort)
    db.query(StockReservation).filter(StockReservation.order_id == order_id).delete(synchronize_session=False)
    db.commit()