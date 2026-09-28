from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import AppError
from app.core.security import create_access_token, verify_password
from app.models import Role, User
from app.models.user import ROLE_LABELS
from app.schemas.auth import DemoLoginIn, LoginIn, PersonaOut, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

ROLE_ORDER = {Role.BDM: 0, Role.BDE: 1, Role.SM: 2, Role.SE: 3}


def to_user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        name=user.name,
        role=user.role,
        role_label=ROLE_LABELS[Role(user.role)],
        phone=user.phone,
    )


def _token(user: User) -> TokenOut:
    return TokenOut(access_token=create_access_token(str(user.id), user.role), user=to_user_out(user))


@router.get("/personas", response_model=list[PersonaOut])
def list_personas(db: Session = Depends(get_db)) -> list[PersonaOut]:
    """Seeded demo users, for the persona picker. Empty when demo mode is off."""
    if not get_settings().demo_mode:
        return []
    users = db.scalars(select(User).where(User.is_active)).all()
    users = sorted(users, key=lambda u: (ROLE_ORDER[Role(u.role)], u.name))
    return [
        PersonaOut(
            username=u.username, name=u.name, role=u.role, role_label=ROLE_LABELS[Role(u.role)]
        )
        for u in users
    ]


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Wrong username or password", 401)
    return _token(user)


@router.post("/demo-login", response_model=TokenOut)
def demo_login(body: DemoLoginIn, db: Session = Depends(get_db)) -> TokenOut:
    if not get_settings().demo_mode:
        raise AppError("DEMO_DISABLED", "Demo login is disabled", 403)
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None or not user.is_active:
        raise AppError("INVALID_CREDENTIALS", "Unknown demo user", 401)
    return _token(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return to_user_out(user)
