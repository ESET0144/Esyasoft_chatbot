from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from datetime import datetime, timedelta

SECRET_KEY = "dev-secret"
ALGORITHM = "HS256"

def authenticate_user(username: str, password: str):
    # demo users
    # Normalize inputs (IMPORTANT)
    username = username.strip()
    password = password.strip()
    users = {
        "admin": {"username": "admin", "password": "admin", "role": "admin"},
        "user": {"username": "user", "password": "user", "role": "user"},
    }
    user = users.get(username)
    if user and user["password"] == password:
        return user
    return None

def create_access_token(data: dict, expires_minutes: int = 60):
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=expires_minutes)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

class JWTBearer(HTTPBearer):
    async def __call__(self, request: Request):
        # MUST await parent
        credentials: HTTPAuthorizationCredentials = await super().__call__(request)

        if not credentials:
            raise HTTPException(status_code=403, detail="Missing token")

        try:
            payload = jwt.decode(
                credentials.credentials,
                SECRET_KEY,
                algorithms=[ALGORITHM]
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=403, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=403, detail="Invalid token")
