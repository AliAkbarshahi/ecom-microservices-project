from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from typing import List, Dict
from .. import schemas, crud
from ..database import get_db
import datetime as dt

from ..external_services import  get_product_info
from ..messaging import publish_event
from ..auth import get_current_user, get_current_admin

router = APIRouter(
    prefix="/orders",
    tags=["Order Service"]
)

# Security scheme for Bearer token
security = HTTPBearer()


@router.post("/", response_model=schemas.OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    order_data: schemas.OrderCreate,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    
    try:
        user_id = current_user["id"]
        
        # Process each item: get product info, check stock (NO stock update here)
        items_data = []
        for item in order_data.items:
            # Get product information from product service
            product_info = get_product_info(item.product_id)
            
            # Check stock availability
            if product_info["stock"] < item.quantity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Insufficient stock for product '{product_info['name']}' (ID: {item.product_id}). "
                           f"Available: {product_info['stock']}, Requested: {item.quantity}"
                )
            
            # Prepare item data for order creation
            items_data.append({
                "product_id": item.product_id,
                "product_name": product_info["name"],
                "quantity": item.quantity,
                "price": product_info["price"]
            })
        
        # Create order
        db_order = crud.create_order(
            db=db,
            user_id=user_id,
            items_data=items_data
        )

        # Emit: order.created
        publish_event(
            "order.created",
            {
                "event": "order.created",
                "occurred_at": dt.datetime.utcnow().isoformat() + "Z",
                "order_id": db_order.id,
                "user_id": db_order.user_id,
                "total_amount": float(db_order.total_amount),
                "items": [
                    {"product_id": i.product_id, "quantity": i.quantity}
                    for i in db_order.items
                ],
            },
        )
        return db_order
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create order: {str(e)}"
        )


@router.get("/", response_model=schemas.OrderListResponse)
def get_orders(
    skip: int = 0,
    limit: int = 100,
    current_admin: Dict = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
   
    orders = crud.get_orders(db=db, skip=skip, limit=limit)
    total = crud.get_order_count(db=db)

    return {
        "orders": orders,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get("/{order_id}",  response_model=List[schemas.OrderOut])
def get_order(
    order_id: int,
    current_admin: Dict = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
   
    db_order = crud.get_order(db=db, order_id=order_id)
    if not db_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with id {order_id} not found"
        )
    return db_order


@router.get("/me",  response_model=schemas.OrderListResponse)
def get_user_orders(
    skip: int = 0,
    limit: int = 100,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
   
    user_id = current_user["id"]

    orders = crud.get_orders_by_user(db=db, user_id=user_id, skip=skip, limit=limit)
    total = crud.get_user_order_count(db=db, user_id=user_id)

    return {
        "orders": orders,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.patch("/{order_id}/status", response_model=schemas.OrderOut)
def update_order_status(
    order_id: int,
    status_update: schemas.OrderUpdate,
    db: Session = Depends(get_db)
):
    
    db_order = crud.update_order_status(
        db=db,
        order_id=order_id,
        new_status=status_update.status.value
    )
    
    if not db_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with id {order_id} not found"
        )
    
    return db_order


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(
    order_id: int,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
   
    db_order = crud.get_order(db=db, order_id=order_id)

    if not db_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with id {order_id} not found"
        )

    if db_order.user_id != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to delete this order"
        )

    crud.delete_order(db=db, order_id=order_id)

    return None