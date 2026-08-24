from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy
from src.core.config import settings


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(
        secret=settings.SECRET_KEY,
        lifetime_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=BearerTransport(tokenUrl="/auth/jwt/login"),
    get_strategy=get_jwt_strategy,
)
