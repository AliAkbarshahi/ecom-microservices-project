from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from typing import Dict
from .. import schemas, crud
from ..database import get_db
import datetime as dt


from ..external_services import (
    get_product_info,
    reserve_stock_for_order,
    release_stock_reservation,
)
from ..messaging import publish_event
from ..auth import get_current_user, get_current_admin

router = APIRouter(
    prefix="/orders",
    tags=["Order Service"]
)

# Security scheme for Bearer token
security = HTTPBearer()


def _is_active_checkout(db_order) -> bool:
    """Return True if the order is in checkout_pending and reservation window hasn't expired."""
    if not db_order:
        return False
    if getattr(db_order, "status", None) != "checkout_pending":
        return False
    exp = getattr(db_order, "checkout_expires_at", None)
    if not exp:
        return False
    now = dt.datetime.now(dt.timezone.utc)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=dt.timezone.utc)
    return exp > now


def _ensure_cart_editable(db_order) -> None:
    if _is_active_checkout(db_order):
        exp = db_order.checkout_expires_at
        if exp is not None and exp.tzinfo is None:
            exp = exp.replace(tzinfo=dt.timezone.utc)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "cart_locked_during_checkout",
                "message": "Your cart is reserved for checkout. Complete or cancel payment, then try again.",
                "reserved_until": exp.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z") if exp else None,
            },
        )


@router.post("/", response_model=schemas.OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    product_id: int = Form(..., gt=0, description="Product ID", examples=[""]),
    quantity: int = Form(..., gt=0, description="Product quantity", examples=[""]),
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new active cart (pending order) for the current user.

    Notes:
    - This endpoint accepts a single (product_id, quantity) pair via form-data.
    - Each user can have ONLY ONE active cart (pending order). If a cart already exists,
      use PATCH /orders/cart to update quantities and add more products.
    """

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

    _ensure_cart_editable(db_order)

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



@router.put("/cart/item", response_model=schemas.OrderOut)
def edit_cart_item(
    product_id: int = Form(..., gt=0, description="Product ID", examples=[""]),
    quantity: int = Form(..., gt=0, description="New product quantity", examples=[""]),
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Edit an existing product inside the current user's active cart (pending order).

    - No order_id is required; it's inferred from the authorized user.
    - This endpoint only EDITS items that already exist in the cart.
      If you want to add a new product to the cart, use PATCH /orders/cart.
    """

    user_id = current_user["id"]
    db_order = crud.get_active_cart_by_user(db=db, user_id=user_id)
    if db_order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active cart (pending order) found for this user",
        )

    _ensure_cart_editable(db_order)

    if not any(i.product_id == product_id for i in (db_order.items or [])):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This product is not in your cart. Use PATCH /orders/cart to add it first.",
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

    return crud.upsert_cart_items(db=db, db_order=db_order, items_data=items_data)


@router.delete("/cart/item", status_code=status.HTTP_204_NO_CONTENT)
def delete_cart_item(
    product_id: int = Form(..., gt=0, description="Product ID", examples=[""]),
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a product from the current user's active cart (pending order)."""

    user_id = current_user["id"]
    db_order = crud.get_active_cart_by_user(db=db, user_id=user_id)
    if db_order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active cart (pending order) found for this user",
        )

    _ensure_cart_editable(db_order)

    if not any(i.product_id == product_id for i in (db_order.items or [])):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This product is not in your cart",
        )

    # quantity == 0 => remove
    crud.upsert_cart_items(
        db=db,
        db_order=db_order,
        items_data=[{"product_id": product_id, "quantity": 0}],
    )
    return None


# -----------------------------
# Checkout (reserve inventory + go to payment)
# -----------------------------


def _parse_iso_z(value: str) -> dt.datetime:
    """Parse ISO8601 string that may end with 'Z'."""
    if not value:
        raise ValueError("invalid_datetime")
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(v)
    # Ensure timezone-aware UTC datetime
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


@router.post("/checkout")
def checkout_my_cart(
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reserve items in the user's cart for a short period (1 minute) and return payment URLs.

    - No order_id is required.
    - If reservation already exists and hasn't expired, returns the same reserved_until.
    """

    user_id = current_user["id"]
    db_order = crud.get_active_cart_by_user(db=db, user_id=user_id)
    if db_order is None:
        raise HTTPException(status_code=404, detail="No active cart found for this user")

    if not (db_order.items or []):
        raise HTTPException(status_code=400, detail="Your cart is empty")

    now = dt.datetime.now(dt.timezone.utc)

    # If user already in an active checkout window, don't create another reservation
    exp = db_order.checkout_expires_at
    if exp is not None and exp.tzinfo is None:
        exp = exp.replace(tzinfo=dt.timezone.utc)

    if db_order.status == "checkout_pending" and exp and exp > now:
        reserved_until = exp
        return {
            "order_id": db_order.id,
            "status": "checkout_pending",
            "total_amount": float(db_order.total_amount),
            "reserved_until": reserved_until.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            "payment": {
                "succeed": "/payments/succeed",
                "fail": "/payments/fail",
            },
        }

    # Expired checkout: release old reservation and move order to cancelled (items stay)
    if db_order.status == "checkout_pending" and exp and exp <= now:
        release_stock_reservation(order_id=db_order.id)
        db_order.status = "cancelled"
        db_order.checkout_expires_at = None
        db.commit()
        db.refresh(db_order)

    # Try to reserve stock in product-service for 60 seconds
    reserve_resp = reserve_stock_for_order(
        order_id=db_order.id,
        user_id=db_order.user_id,
        items=[{"product_id": i.product_id, "quantity": i.quantity} for i in db_order.items],
        ttl_seconds=60,
    )
    reserved_until = _parse_iso_z(reserve_resp.get("reserved_until"))

    db_order.status = "checkout_pending"
    db_order.checkout_expires_at = reserved_until
    db.commit()
    db.refresh(db_order)

    # Normalize reserved_until for output
    if reserved_until.tzinfo is None:
        reserved_until = reserved_until.replace(tzinfo=dt.timezone.utc)
    return {
        "order_id": db_order.id,
        "status": "checkout_pending",
        "total_amount": float(db_order.total_amount),
        "reserved_until": reserved_until.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "payment": {
            "succeed": "/payments/succeed",
            "fail": "/payments/fail",
        },
    }


@router.get("/checkout")
def get_my_checkout(
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return current checkout session (used by payment-service).

    - No order_id is required.
    - Returns 404 if the user has no active checkout.
    """
    user_id = current_user["id"]
    order = crud.get_active_checkout_by_user(db=db, user_id=user_id)
    if not order:
        raise HTTPException(status_code=404, detail="No active checkout found")

    return {
        "order_id": order.id,
        "total_amount": float(order.total_amount),
        "reserved_until": (
            (order.checkout_expires_at.replace(tzinfo=dt.timezone.utc) if order.checkout_expires_at and order.checkout_expires_at.tzinfo is None else order.checkout_expires_at)
            .astimezone(dt.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
            if order.checkout_expires_at
            else None
        ),
    }

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