import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, Form
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional, Dict
from ..database import get_db
from ..crud import (
    create_product,
    get_product,
    get_products,
    update_product,
    delete_product,
    create_reservations,
    release_reservations,
)
from ..schemas import ProductOut
from ..auth import get_current_user, get_current_admin

router = APIRouter(prefix="/products", tags=["Product Service"])


class ReservationItem(BaseModel):
    product_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0)


class ReservationRequest(BaseModel):
    order_id: int = Field(..., gt=0)
    user_id: int = Field(..., gt=0)
    ttl_seconds: int = Field(60, ge=10, le=600)
    items: list[ReservationItem] = Field(..., min_length=1)


class ReservationResponse(BaseModel):
    order_id: int
    reserved_until: str

@router.post("/", response_model=ProductOut, status_code=201)
def Create_Products_Only_Admin(
    name: str = Form(..., description="**Product name** (required)", examples=[""]),
    description: Optional[str] = Form(None, description="**Description** (optional)", examples=[""]),
    price: float = Form(..., gt=0, description="**Price** (must be greater than 0)", examples=[""]),
    stock: int = Form(..., ge=0, description="**Stock quantity** (must be >= 0)", examples=[""]),
    category: Optional[str] = Form(None, description="**Category** (optional)", examples=[""]),
    current_admin: Dict = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    product_data = {
        "name": name,
        "description": description,
        "price": price,
        "stock": stock,
        "category": category
    }
    try:
        return create_product(db, product_data)
    except ValueError as e:
        if str(e) == "duplicate_product_name":
            raise HTTPException(status_code=409, detail="Product name already exists")
        if str(e) == "name_required":
            raise HTTPException(status_code=400, detail="Product name is required")
        raise HTTPException(status_code=400, detail=str(e))
    except IntegrityError:
        # DB-level unique constraint (race conditions)
        db.rollback()
        raise HTTPException(status_code=409, detail="Product name already exists")


@router.get("/", response_model=list[ProductOut])
def View_Products(
    skip: int = Query(0, ge=0, description="**Skip** number of products", examples=[""]),
    limit: int = Query(100, ge=1, le=1000, description="**Limit** number of products", examples=[""]),
    search: Optional[str] = Query(None, description="**Search** in name, description, or category", examples=[""]),
   # current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_products(db, skip=skip, limit=limit, search=search)


@router.get("/{product_id}", response_model=ProductOut)
def View_Product(
    product_id: int,
    #current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    product = get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.patch("/{product_id}", response_model=ProductOut)
def Update_Product_Only_Admin(
    product_id: int,
    name: Optional[str] = Form(None, description="**New name** (optional)", examples=[""]),
    description: Optional[str] = Form(None, description="**New description** (optional)", examples=[""]),
    price: Optional[float] = Form(None, gt=0, description="**New price** (optional, > 0)", examples=[""]),
    stock: Optional[int] = Form(None, ge=0, description="**New stock** (optional, >= 0)", examples=[""]),
    category: Optional[str] = Form(None, description="**New category** (optional)", examples=[""]),
    current_admin: Dict = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    update_data = {
        "name": name,
        "description": description,
        "price": price,
        "stock": stock,
        "category": category
    }
    update_data = {k: v for k, v in update_data.items() if v is not None}
    
    try:
        product = update_product(db, product_id, update_data)
    except ValueError as e:
        if str(e) == "duplicate_product_name":
            raise HTTPException(status_code=409, detail="Product name already exists")
        if str(e) == "name_required":
            raise HTTPException(status_code=400, detail="Product name is required")
        raise HTTPException(status_code=400, detail=str(e))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Product name already exists")
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.delete("/{product_id}", response_model=ProductOut)
def Delete_Product_Only_Admin(
    product_id: int,
    current_admin: Dict = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    product = delete_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


# -----------------------------
# Reservations (used by checkout)
# -----------------------------


@router.post("/reservations", response_model=ReservationResponse)
def reserve_stock_for_checkout(
    body: ReservationRequest,
    db: Session = Depends(get_db),
):
    """Create/refresh short-lived reservations for an order.

    This endpoint is intended to be called by Order Service during checkout.
    """

    try:
        reserved_until = create_reservations(
            db,
            order_id=body.order_id,
            user_id=body.user_id,
            items=[i.model_dump() for i in body.items],
            ttl_seconds=body.ttl_seconds,
        )
        if reserved_until.tzinfo is None:
            reserved_until = reserved_until.replace(tzinfo=dt.timezone.utc)
        return {
            "order_id": body.order_id,
            "reserved_until": reserved_until.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    except ValueError as e:
        msg = str(e)
        if msg.startswith("insufficient_available_stock:"):
            # format: insufficient_available_stock:<pid>:<available>:<requested>
            _, pid, available, requested = msg.split(":", 3)
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "insufficient_stock",
                    "product_id": int(pid),
                    "available": int(available),
                    "requested": int(requested),
                },
            )
        if msg.startswith("product_not_found:"):
            _, pid = msg.split(":", 1)
            raise HTTPException(status_code=404, detail={"error": "product_not_found", "product_id": int(pid)})
        raise HTTPException(status_code=400, detail=msg)


@router.post("/reservations/{order_id}/release")
def release_stock_reservation(
    order_id: int,
    db: Session = Depends(get_db),
):
    """Release all active reservations for an order."""
    deleted = release_reservations(db, order_id=order_id)
    return {"order_id": order_id, "released": deleted}

