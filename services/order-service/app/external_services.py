"""
Helper functions for communicating with other microservices
"""
import os
import requests
from typing import Optional, Dict
from fastapi import HTTPException, status
from dotenv import load_dotenv

load_dotenv()

<<<<<<< HEAD
# Service URLs from environment variables or defaults
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service:8000")
PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8000")

# Shared SECRET_KEY for token validation (should match user-service)
=======
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service:8000")
PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8000")

>>>>>>> fdbe25c0d9d4e2484f4657400bb0089ba83c335d
SECRET_KEY = os.getenv("SECRET_KEY", "8f3b9e7a2c4d1f5e6a8b0c9d3e7f2a1b4c6d8e9f0a5b7c2d1e3f4a6b8c9d0e1f2")
ALGORITHM = "HS256"


def get_user_id_from_token(token: str) -> int:
<<<<<<< HEAD
    """
    Get user ID from JWT token by calling user service
    
    Args:
        token: JWT token string
        
    Returns:
        User ID
        
    Raises:
        HTTPException: If token is invalid or user not found
    """
    try:
        # Call user service to get user info from token
        # URL encode the endpoint path to handle spaces in "my profile"
        headers = {"Authorization": f"Bearer {token}"}
        # Replace space with %20 for URL encoding
=======
    
    try:
       
        headers = {"Authorization": f"Bearer {token}"}
>>>>>>> fdbe25c0d9d4e2484f4657400bb0089ba83c335d
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
<<<<<<< HEAD
    """
    Get product information from product service
    
    Args:
        product_id: ID of the product
        
    Returns:
        Dictionary containing product info (id, name, price, stock)
        
    Raises:
        HTTPException: If product not found or service unavailable
    """
=======
 
>>>>>>> fdbe25c0d9d4e2484f4657400bb0089ba83c335d
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
<<<<<<< HEAD
    """
    Update product stock by subtracting the ordered quantity
    
    Args:
        product_id: ID of the product
        quantity_to_subtract: Quantity to subtract from stock
        
    Returns:
        True if successful
        
    Raises:
        HTTPException: If update fails or service unavailable
    """
=======
   
>>>>>>> fdbe25c0d9d4e2484f4657400bb0089ba83c335d
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

