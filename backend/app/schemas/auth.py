import uuid

from pydantic import BaseModel, ConfigDict


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    name: str
    role: str
    role_label: str
    phone: str | None = None


class PersonaOut(BaseModel):
    username: str
    name: str
    role: str
    role_label: str


class LoginIn(BaseModel):
    username: str
    password: str


class DemoLoginIn(BaseModel):
    username: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
