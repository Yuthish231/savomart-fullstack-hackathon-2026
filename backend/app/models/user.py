from enum import StrEnum

from sqlalchemy import CheckConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import APP, Base, Timestamps, UUIDPk


class Role(StrEnum):
    BDM = "BDM"  # BD Manager
    BDE = "BDE"  # BD Executive
    SM = "SM"  # Survey Manager
    SE = "SE"  # Survey Executive


ROLE_LABELS = {
    Role.BDM: "BD Manager",
    Role.BDE: "BD Executive",
    Role.SM: "Survey Manager",
    Role.SE: "Survey Executive",
}


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "user"
    __table_args__ = (
        CheckConstraint("role IN ('BDM','BDE','SM','SE')", name="role_valid"),
        Index("ix_app_user_role", "role"),
        {"schema": APP},
    )

    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(8), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
