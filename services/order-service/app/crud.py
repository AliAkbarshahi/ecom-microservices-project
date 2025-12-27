from sqlalchemy.orm import Session
from decimal import Decimal
from .models import Order, OrderItem
from typing import List, Optional, Dict

def create_order(db: Session, user_id: int, items_data: List[dict]) -> Order:
   
    # Calculate total amount
    total_amount = sum(
        Decimal(str(item['price'])) * item['quantity'] 
        for item in items_data
    )
    
    # Create order
    db_order = Order(
        user_id=user_id,
        total_amount=total_amount,
        status="pending"
    )
    db.add(db_order)
    db.flush()  # Get order ID without committing
    
    # Create order items
    for item_data in items_data:
        order_item = OrderItem(
            order_id=db_order.id,
            product_id=item_data['product_id'],
            product_name=item_data['product_name'],
            quantity=item_data['quantity'],
            price=item_data['price']
        )
        db.add(order_item)
    
    db.commit()
    db.refresh(db_order)
    return db_order


def get_order(db: Session, order_id: int) -> Optional[Order]:
  
    return db.query(Order).filter(Order.id == order_id).first()


def get_orders(db: Session, skip: int = 0, limit: int = 100) -> List[Order]:
   
    return db.query(Order).offset(skip).limit(limit).all()


def get_orders_by_user(db: Session, user_id: int, skip: int = 0, limit: int = 100) -> List[Order]:
    
    return db.query(Order).filter(Order.user_id == user_id).offset(skip).limit(limit).all()


def get_active_cart_by_user(db: Session, user_id: int) -> Optional[Order]:
    """Return the user's active cart.

    We treat the following as "cart" states (unpaid orders):
    - pending
    - checkout_pending (during reservation window)
    - cancelled (checkout failed; items stay so user can retry)
    """

    return (
        db.query(Order)
        .filter(
            Order.user_id == user_id,
            Order.payment_status.is_(False),
            Order.status.in_(["pending", "checkout_pending", "cancelled"]),
        )
        .order_by(Order.id.desc())
        .first()
    )


def get_active_checkout_by_user(db: Session, user_id: int) -> Optional[Order]:
    """Return the user's current checkout session if still valid.

    Important: We do NOT filter by checkout_expires_at at SQL level.
    Some DBs/session timezones can cause timestamptz comparisons with naive
    datetimes to behave unexpectedly. We fetch the latest checkout_pending order
    and validate the TTL in Python after normalizing to UTC.
    """
    import datetime as dt

    order = (
        db.query(Order)
        .filter(
            Order.user_id == user_id,
            Order.payment_status.is_(False),
            Order.status == "checkout_pending",
            Order.checkout_expires_at.isnot(None),
        )
        .order_by(Order.id.desc())
        .first()
    )

    if not order or not order.checkout_expires_at:
        return None

    now = dt.datetime.now(dt.timezone.utc)
    exp = order.checkout_expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=dt.timezone.utc)

    return order if exp > now else None


def recalc_order_total(db_order: Order) -> None:
    db_order.total_amount = sum(
        (Decimal(str(item.price)) * item.quantity) for item in (db_order.items or [])
    )


def upsert_cart_items(db: Session, db_order: Order, items_data: List[Dict]) -> Order:
    """Upsert order items and recalculate totals.

    items_data format:
    [{
        "product_id": int,
        "product_name": str,
        "quantity": int (>=0),
        "price": number
    }, ...]
    - quantity==0 removes the item if it exists.
    """

    existing_by_product_id = {item.product_id: item for item in (db_order.items or [])}

    for item in items_data:
        pid = int(item["product_id"])
        qty = int(item["quantity"])

        if qty == 0:
            # Remove if present
            existing = existing_by_product_id.get(pid)
            if existing is not None:
                db.delete(existing)
            continue

        existing = existing_by_product_id.get(pid)
        if existing is None:
            db.add(
                OrderItem(
                    order_id=db_order.id,
                    product_id=pid,
                    product_name=item["product_name"],
                    quantity=qty,
                    price=item["price"],
                )
            )
        else:
            existing.product_name = item["product_name"]
            existing.quantity = qty
            existing.price = item["price"]

    # Ensure ORM relationship is up to date
    db.flush()
    db.refresh(db_order)
    recalc_order_total(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order


def update_order_status(db: Session, order_id: int, new_status: str) -> Optional[Order]:
   
    db_order = get_order(db, order_id)
    if not db_order:
        return None
    
    db_order.status = new_status
    db.commit()
    db.refresh(db_order)
    return db_order


def mark_order_paid(db: Session, order_id: int) -> Optional[Order]:
   
    db_order = get_order(db, order_id)
    if not db_order:
        return None

    db_order.payment_status = True
    # keep your existing status enum values
    db_order.status = "confirmed"
    db_order.checkout_expires_at = None
    db.commit()
    db.refresh(db_order)
    return db_order


def delete_order(db: Session, order_id: int) -> Optional[Order]:
    
    db_order = get_order(db, order_id)
    if db_order:
        db.delete(db_order)
        db.commit()
    return db_order


def get_order_count(db: Session) -> int:
    
    return db.query(Order).count()


def get_user_order_count(db: Session, user_id: int) -> int:
    
    return db.query(Order).filter(Order.user_id == user_id).count()