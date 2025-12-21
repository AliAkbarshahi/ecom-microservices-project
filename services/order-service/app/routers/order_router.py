
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import List
from .. import schemas, crud
from ..database import get_db
from ..external_services import get_user_id_from_token, get_product_info, update_product_stock

router = APIRouter(
    prefix="/orders",
    tags=["Order Service"]
)

# Security scheme for Bearer token
security = HTTPBearer()


@router.post("/", response_model=schemas.OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    order_data: schemas.OrderCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    
<<<<<<< HEAD
    - **Authorization**: Bearer token (required)
    - **items**: List of products with product_id and quantity
    
    The service will:
    1. Extract user_id from the token
    2. Get product information (name, price, stock) from product service
    3. Check stock availability
    4. Update product stock
    5. Create order with product names
    """
=======
>>>>>>> fdbe25c0d9d4e2484f4657400bb0089ba83c335d
    try:
        # Extract token from credentials
        token = credentials.credentials
        
        # Get user_id from token
        user_id = get_user_id_from_token(token)
        
        # Process each item: get product info, check stock, update stock
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
            
            # Update product stock (subtract ordered quantity)
            update_product_stock(item.product_id, item.quantity)
            
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
    db: Session = Depends(get_db)
):
    
    db_order = crud.get_order(db=db, order_id=order_id)
    if not db_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with id {order_id} not found"
        )
    return db_order


@router.get("/user/{user_id}",  response_model=List[schemas.OrderOut])
def get_user_orders(
    user_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    
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
    db: Session = Depends(get_db)
):
    
    db_order = crud.delete_order(db=db, order_id=order_id)
    
    if not db_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with id {order_id} not found"
        )
    
    return None