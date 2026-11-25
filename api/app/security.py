from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import User

_ph = PasswordHasher()  # Argon2id by default
COOKIE = "session"


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(hashed: str, pw: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except VerifyMismatchError:
        return False


def make_token(payload: dict, ttl: timedelta) -> str:
    data = {**payload, "exp": datetime.now(UTC) + ttl}
    return jwt.encode(data, get_settings().jwt_secret, algorithm="HS256")


def read_token(token: str | None) -> dict | None:
    if not token:
        return None
    try:
        return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def session_token(user: User) -> str:
    return make_token({"sub": str(user.id), "role": user.role}, timedelta(hours=get_settings().session_hours))


class LoginRequired(Exception):
    """Raised for HTML pages; the app redirects to /login."""


async def optional_user(request: Request, db: AsyncSession = Depends(get_db)) -> User | None:
    data = read_token(request.cookies.get(COOKIE))
    if not data:
        return None
    return await db.get(User, int(data["sub"]))


def require_role(*roles: str):
    async def dep(request: Request, user: User | None = Depends(optional_user)) -> User:
        if user is None:
            if request.url.path.startswith("/api/"):
                raise HTTPException(401, "Not authenticated")
            raise LoginRequired
        if roles and user.role not in roles:
            raise HTTPException(403, "Forbidden for your role")
        return user

    return dep
