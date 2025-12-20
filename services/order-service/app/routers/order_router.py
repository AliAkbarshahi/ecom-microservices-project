
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from .. import schemas, crud
from ..database import get_db

router = APIRouter(
    prefix="/api/orders",
    tags=["orders"]
)


@router.post("/", response_model=schemas.OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    order_data: schemas.OrderCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new order
    
    - **user_id**: ID of the user placing the order
    - **items**: List of products with quantity and price
    """
    try:
        # Convert items to dict format for CRUD function
        items_data = [item.model_dump() for item in order_data.items]
        
        # Create order
        db_order = crud.create_order(
            db=db,
            user_id=order_data.user_id,
            items_data=items_data
        )
        return db_order
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create order: {str(e)}"
        )


@router.get("/", response_model=schemas.OrderListResponse)
def get_orders(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    Get list of all orders with pagination
    
    - **skip**: Number of records to skip (default: 0)
    - **limit**: Maximum number of records to return (default: 100)
    """
    orders = crud.get_orders(db=db, skip=skip, limit=limit)
    total = crud.get_order_count(db=db)
    
    return {
        "orders": orders,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get("/{order_id}", response_model=schemas.OrderOut)
def get_order(
    order_id: int,
    db: Session = Depends(get_db)
):
    """
    Get a specific order by ID
    
    - **order_id**: ID of the order
    """
    db_order = crud.get_order(db=db, order_id=order_id)
    if not db_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with id {order_id} not found"
        )
    return db_order


@router.get("/user/{user_id}", response_model=schemas.OrderListResponse)
def get_user_orders(
    user_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    Get all orders for a specific user
    
    - **user_id**: ID of the user
    - **skip**: Number of records to skip (default: 0)
    - **limit**: Maximum number of records to return (default: 100)
    """
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
    """
    Update the status of an order
    
    - **order_id**: ID of the order
    - **status**: New status value (pending, confirmed, processing, shipped, delivered, cancelled, failed)
    """
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
    db: Session = Depends(get_db)
):
    """
    Delete an order
    
    - **order_id**: ID of the order to delete
    """
    db_order = crud.delete_order(db=db, order_id=order_id)
    
    if not db_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with id {order_id} not found"
        )
    
    return None