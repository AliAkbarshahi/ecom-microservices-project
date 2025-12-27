"""
Helper functions for communicating with other microservices
"""
import os
import requests
from typing import Optional, Dict
from fastapi import HTTPException, status
from dotenv import load_dotenv

load_dotenv()

USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service:8000")
PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8000")

SECRET_KEY = os.getenv("SECRET_KEY", "8f3b9e7a2c4d1f5e6a8b0c9d3e7f2a1b4c6d8e9f0a5b7c2d1e3f4a6b8c9d0e1f2")
ALGORITHM = "HS256"


def get_user_id_from_token(token: str) -> int:
    
    try:
       
        headers = {"Authorization": f"Bearer {token}"}
        endpoint = "/users/my profile".replace(" ", "%20")
        response = requests.get(
            f"{USER_SERVICE_URL}{endpoint}",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            user_data = response.json()
            return user_data["id"]
        elif response.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get user from user service: {response.text}"
            )
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"User service is unavailable: {str(e)}"
        )


def get_product_info(product_id: int) -> Dict:
 
    try:
        response = requests.get(
            f"{PRODUCT_SERVICE_URL}/products/{product_id}",
            timeout=5
        )
        
        if response.status_code == 200:
            product_data = response.json()
            return {
                "id": product_data["id"],
                "name": product_data["name"],
                "price": float(product_data["price"]),
                "stock": product_data["stock"]
            }
        elif response.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with id {product_id} not found"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get product from product service: {response.text}"
            )
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Product service is unavailable: {str(e)}"
        )


def update_product_stock(product_id: int, quantity_to_subtract: int) -> bool:
   
    try:
        # First get current product info
        product_info = get_product_info(product_id)
        current_stock = product_info["stock"]
        new_stock = current_stock - quantity_to_subtract
        
        if new_stock < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock for product {product_id}. Available: {current_stock}, Requested: {quantity_to_subtract}"
            )
        
        # Update product stock
        response = requests.patch(
            f"{PRODUCT_SERVICE_URL}/products/{product_id}",
            data={"stock": new_stock},
            timeout=5
        )
        
        if response.status_code == 200:
            return True
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update product stock: {response.text}"
            )
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Product service is unavailable: {str(e)}"
        )


def reserve_stock_for_order(*, order_id: int, user_id: int, items: list[dict], ttl_seconds: int = 60) -> dict:
    """Ask product-service to reserve stock for a short window."""
    try:
        resp = requests.post(
            f"{PRODUCT_SERVICE_URL}/products/reservations",
            json={
                "order_id": int(order_id),
                "user_id": int(user_id),
                "ttl_seconds": int(ttl_seconds),
                "items": [{"product_id": int(i["product_id"]), "quantity": int(i["quantity"])} for i in items],
            },
            timeout=5,
        )
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail=resp.json())
        if resp.status_code == 400:
            raise HTTPException(status_code=400, detail=resp.json())
        raise HTTPException(status_code=500, detail=f"Failed to reserve stock: {resp.text}")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=503, detail=f"Product service is unavailable: {str(e)}")


def release_stock_reservation(*, order_id: int) -> None:
    """Best-effort release of reservations for an order."""
    try:
        requests.post(
            f"{PRODUCT_SERVICE_URL}/products/reservations/{int(order_id)}/release",
            timeout=5,
        )
    except requests.exceptions.RequestException:
        # best-effort; ignore
        return

