import uuid
from collections.abc import Callable

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import AppError, Forbidden
from app.core.security import decode_access_token
from app.models import Role, User

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise AppError("UNAUTHORIZED", "Sign in required", 401)
    try:
        claims = decode_access_token(creds.credentials)
        user_id = uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise AppError("UNAUTHORIZED", "Session expired or invalid, please sign in again", 401)
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError("UNAUTHORIZED", "User no longer active", 401)
    return user


def require_roles(*roles: Role) -> Callable[..., User]:
    """Route guard: `user: User = Depends(require_roles(Role.BDM))`."""

    allowed = {r.value for r in roles}

    def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise Forbidden(f"This action needs role {' or '.join(sorted(allowed))}")
        return user

    return _guard
