import secrets
from fastapi import Depends, HTTPException, security
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from core.config import settings


USERNAME = settings.BASIC_AUTH_USERNAME
PASSWORD = settings.BASIC_AUTH_PASSWORD

security = HTTPBasic()


def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    # Constant time comparison to prevent timing attacks
    is_correct_username = secrets.compare_digest(credentials.username, USERNAME)
    is_correct_password = secrets.compare_digest(credentials.password, PASSWORD)

    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"Content-Type": "application/json"},
        )
    return credentials.username
