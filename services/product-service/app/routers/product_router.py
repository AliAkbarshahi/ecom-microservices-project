from fastapi import APIRouter, Depends, HTTPException, Query, Form
from sqlalchemy.orm import Session
from typing import Optional
from ..database import get_db
from ..crud import create_product, get_product, get_products, update_product, delete_product
from  ..schemas import ProductOut

router = APIRouter(prefix="/products", tags=["Product Service"])

@router.post("/", response_model=ProductOut, status_code=201)
def Create_Products_Only_Admin(
    name: str = Form(..., description="**Product name** (required)", examples=[""]),
    description: Optional[str] = Form(None, description="**Description** (optional)", examples=[""]),
    price: float = Form(..., gt=0, description="**Price** (must be greater than 0)", examples=[""]),
    stock: int = Form(..., ge=0, description="**Stock quantity** (must be >= 0)", examples=[""]),
    category: Optional[str] = Form(None, description="**Category** (optional)", examples=[""]),
    db: Session = Depends(get_db)
):
    product_data = {
        "name": name,
        "description": description,
        "price": price,
        "stock": stock,
        "category": category
    }
    return create_product(db, product_data)


@router.get("/", response_model=list[ProductOut])
def View_Products_Only_Admin(
    skip: int = Query(0, ge=0, description="**Skip** number of products", examples=[""]),
    limit: int = Query(100, ge=1, le=1000, description="**Limit** number of products", examples=[""]),
    search: Optional[str] = Query(None, description="**Search** in name, description, or category", examples=[""]),
    db: Session = Depends(get_db)
):
    return get_products(db, skip=skip, limit=limit, search=search)


@router.get("/{product_id}", response_model=ProductOut)
def View_Product(product_id: int, db: Session = Depends(get_db)):
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
    
    product = update_product(db, product_id, update_data)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.delete("/{product_id}", response_model=ProductOut)
def Delete_Product_Only_Admin(product_id: int, db: Session = Depends(get_db)):
    product = delete_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product