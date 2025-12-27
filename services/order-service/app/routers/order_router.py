from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from typing import Dict
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
    product_id: int = Form(..., gt=0, description="Product ID", examples=[""]),
    quantity: int = Form(..., gt=0, description="Product quantity", examples=[""]),
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    

    try:
        user_id = current_user["id"]

        # Enforce: one active cart (pending order) per user
        existing_cart = crud.get_active_cart_by_user(db=db, user_id=user_id)
        if existing_cart is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "You already have an active cart (pending order). "
                    "Use PATCH /orders/cart to update it or GET /orders/cart to view it."
                ),
            )

        product_info = get_product_info(product_id)

        if product_info["stock"] < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Insufficient stock for product '{product_info['name']}' (ID: {product_id}). "
                    f"Available: {product_info['stock']}, Requested: {quantity}"
                ),
            )

        items_data = [
            {
                "product_id": product_id,
                "product_name": product_info["name"],
                "quantity": quantity,
                "price": product_info["price"],
            }
        ]

        db_order = crud.create_order(db=db, user_id=user_id, items_data=items_data)

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
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create order: {str(e)}",
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


@router.get("/{order_id:int}",  response_model=schemas.OrderOut)
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


@router.get("/cart", response_model=schemas.OrderOut)
def get_my_cart(
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the current user's active cart (pending order).

    This endpoint does NOT require an order_id. It infers the user_id from the Bearer token.
    """

    user_id = current_user["id"]
    db_order = crud.get_active_cart_by_user(db=db, user_id=user_id)
    if db_order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active cart (pending order) found for this user",
        )
    return db_order


# @router.get("/me",  response_model=schemas.OrderListResponse)
# def get_user_orders(
#     skip: int = 0,
#     limit: int = 100,
#     current_user: Dict = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
   
#     user_id = current_user["id"]

#     orders = crud.get_orders_by_user(db=db, user_id=user_id, skip=skip, limit=limit)
#     total = crud.get_user_order_count(db=db, user_id=user_id)

#     return {
#         "orders": orders,
#         "total": total,
#         "skip": skip,
#         "limit": limit
#     }


@router.patch("/cart", response_model=schemas.OrderOut)
def update_my_cart(
    product_id: int = Form(..., gt=0, description="Product ID", examples=[""]),
    quantity: int = Form(..., gt=0, description="Product quantity", examples=[""]),
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upsert a single product inside the current user's active cart (pending order).

    - No order_id is required; it's inferred from the authorized user.
    - This endpoint accepts a single (product_id, quantity) pair via form-data.
    - quantity must be > 0 (to remove an item, add a dedicated DELETE endpoint if needed).
    """

    user_id = current_user["id"]
    db_order = crud.get_active_cart_by_user(db=db, user_id=user_id)
    if db_order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active cart (pending order) found for this user",
        )

    product_info = get_product_info(product_id)

    if product_info["stock"] < quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Insufficient stock for product '{product_info['name']}' (ID: {product_id}). "
                f"Available: {product_info['stock']}, Requested: {quantity}"
            ),
        )

    items_data = [
        {
            "product_id": product_id,
            "product_name": product_info["name"],
            "quantity": quantity,
            "price": product_info["price"],
        }
    ]

    updated_order = crud.upsert_cart_items(db=db, db_order=db_order, items_data=items_data)
    return updated_order


@router.patch("/{order_id:int}/status", response_model=schemas.OrderOut)
def update_order_status(
    order_id: int,
    status_update: schemas.OrderUpdate,
    db: Session = Depends(get_db)
):
    
    if status_update.status is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'status' is required",
        )

    db_order = crud.update_order_status(
        db=db,
        order_id=order_id,
        new_status=status_update.status.value,
    )
    
    if not db_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with id {order_id} not found"
        )
    
    return db_order


@router.delete("/{order_id:int}", status_code=status.HTTP_204_NO_CONTENT)
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