from fastapi_users import FastAPIUsers
from src.models.user import User
from src.auth.backend import auth_backend
from src.auth.manager import get_user_manager
import uuid


fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [auth_backend],
)

# Dependências prontas para usar em qualquer rota
current_active_user = fastapi_users.current_user(active=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)
