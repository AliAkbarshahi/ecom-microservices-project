from sqlalchemy.orm import Session
from decimal import Decimal
from .models import Order, OrderItem
from typing import List, Optional

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