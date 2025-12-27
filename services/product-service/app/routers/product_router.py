from fastapi import APIRouter, Depends, HTTPException, Query, Form
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional, Dict
from ..database import get_db
from ..crud import create_product, get_product, get_products, update_product, delete_product
from ..schemas import ProductOut
from ..auth import  get_current_admin

router = APIRouter(prefix="/products", tags=["Product Service"])

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