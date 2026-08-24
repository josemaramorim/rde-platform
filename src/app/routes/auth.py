from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.app.services.auth_service import hash_password, verify_password, create_token

router = APIRouter()


class AuthData(BaseModel):
    email: str
    password: str


# Mock user database for demo (hashed lazily on first use)
_MOCK_USERS_RAW = {
    "ferreira.jpa1@hotmail.com": "Regy2423$$"
}
_MOCK_USERS: dict = {}


def _get_mock_users():
    if not _MOCK_USERS:
        for email, pwd in _MOCK_USERS_RAW.items():
            _MOCK_USERS[email] = hash_password(pwd)
    return _MOCK_USERS


@router.post("/login")
async def login(data: AuthData):
    users = _get_mock_users()
    hashed_pwd = users.get(data.email)
    if not hashed_pwd or not verify_password(data.password, hashed_pwd):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token({"sub": data.email})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/register")
async def register(data: AuthData):
    users = _get_mock_users()
    if data.email in users:
        raise HTTPException(status_code=400, detail="User already exists")

    users[data.email] = hash_password(data.password)
    return {"message": "User created successfully"}
