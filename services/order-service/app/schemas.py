
from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Optional, List
from datetime import datetime
from enum import Enum

# Define order status enum
class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    FAILED = "failed"

# Schema for order items (products in the order)
class OrderItemBase(BaseModel):
    product_id: int = Field(..., gt=0, description="Product ID")
    quantity: int = Field(..., gt=0, description="Product quantity")
    price: Decimal = Field(..., gt=0, description="Unit price of product")

class OrderItemCreate(BaseModel):
  
    product_id: int = Field(..., gt=0, description="Product ID")
    quantity: int = Field(..., gt=0, description="Product quantity")

class OrderItemOut(BaseModel):
   
    id: int
    order_id: int
    product_id: int
    product_name: str
    quantity: int
    price: Decimal
    
    model_config = {"from_attributes": True}


# Schema   
class OrderBase(BaseModel):
    user_id: int = Field(..., gt=0, description="User-id")

class OrderCreate(BaseModel):
    
    items: List[OrderItemCreate] = Field(..., min_length=1, description="List of order items")

class OrderUpdate(BaseModel):
    status: Optional[OrderStatus] = None

class OrderOut(BaseModel):
    id: int
    user_id: int
    total_amount: Decimal
    status: OrderStatus
    created_at: datetime
    updated_at: Optional[datetime] = None
    items: List[OrderItemOut] = []
    
    model_config = {"from_attributes": True}


# Schema for API responses
class OrderListResponse(BaseModel):
    orders: List[OrderOut]
    total: int
    skip: int
    limit: int