import os
import requests
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from typing import Dict

load_dotenv()

# Service URLs from environment variables or defaults
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service:8000")

# Security scheme for Bearer token
security = HTTPBearer()


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    
    token = credentials.credentials

    try:
        # Call user service to get user info from token
        headers = {"Authorization": f"Bearer {token}"}
        # Replace space with %20 for URL encoding
        endpoint = "/users/my profile".replace(" ", "%20")
        response = requests.get(
            f"{USER_SERVICE_URL}{endpoint}",
            headers=headers,
            timeout=5
        )

        if response.status_code == 200:
            user_data = response.json()
            return {
                "id": user_data["id"],
                "username": user_data["username"],
                "email": user_data["email"],
                "is_admin": user_data.get("is_admin", False)
            }
        elif response.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
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


def get_current_admin(current_user: Dict = Depends(get_current_user)) -> Dict:
   
    is_admin = current_user.get("is_admin", False)
    # Also check username for admin user
    if current_user.get("username") == "admin":
        is_admin = True

    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions. Admin access required."
        )

    return current_user


