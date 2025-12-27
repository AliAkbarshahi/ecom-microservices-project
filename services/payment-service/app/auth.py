import os
import requests
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict

load_dotenv()

USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service:8000")

security = HTTPBearer()


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    """Validate the Bearer token by calling user-service."""
    token = credentials.credentials
    try:
        headers = {"Authorization": f"Bearer {token}"}
        endpoint = "/users/my profile".replace(" ", "%20")
        resp = requests.get(f"{USER_SERVICE_URL}{endpoint}", headers=headers, timeout=5)

        if resp.status_code == 200:
            user_data = resp.json()
            return {
                "id": user_data["id"],
                "username": user_data["username"],
                "email": user_data.get("email"),
                "is_admin": user_data.get("is_admin", False),
                "token": token,
            }

        if resp.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate user token: {resp.text}",
        )

    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"User service is unavailable: {str(e)}",
        )
