from uuid import UUID
from typing import Optional
from fastapi_users.schemas import BaseUser, BaseUserCreate, BaseUserUpdate
from pydantic import ConfigDict


class UserRead(BaseUser[UUID]):
    username: str
    broker: str
    stake: float
    risk_mode: str
    total_profit: float
    is_admin: bool

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseUserCreate):
    username: str
    broker: str = "iqoption"
    stake: float = 1.0
    risk_mode: str = "safe"


class UserUpdate(BaseUserUpdate):
    username: Optional[str] = None
    broker: Optional[str] = None
    stake: Optional[float] = None
    risk_mode: Optional[str] = None
    api_token: Optional[str] = None
    iq_email: Optional[str] = None
    iq_password: Optional[str] = None
