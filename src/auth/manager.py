"""
User Manager logic for FastAPI Users integration.
"""
import logging
import uuid
from typing import Optional
from fastapi import Depends, Request
from fastapi_users import BaseUserManager, UUIDIDMixin
from src.models.user import User
from src.auth.database import get_user_db
from src.core.config import settings
from src.email_service import send_password_reset_email

FRONTEND_URL = (settings.FRONTEND_URL or "http://localhost:3000").rstrip("/")

logger = logging.getLogger(__name__)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    """
    Custom User Manager for FastAPI Users.
    Handles user lifecycle events like registration and password reset.
    """
    reset_password_token_secret = settings.SECRET_KEY
    verification_token_secret = settings.SECRET_KEY

    async def on_after_register(
        self, user: User, request: Optional[Request] = None
    ):
        """
        Executed after a successful user registration.
        """
        _ = request
        logger.info(f"User registered: {user.email} (ID: {user.id})")
        
        # 🚀 SE VOCÊ QUISER QUE ELE PEÇA VALIDAÇÃO ASSIM QUE SE CADASTRAR:
        # Você pode forçar a geração do token aqui e enviar por e-mail, ou chamar:
        # await self.request_verify(user, request)

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        """
        Executed when a user requests a password reset.
        """
        _ = request
        logger.info(f"Password reset requested for: {user.email}")
        try:
            await send_password_reset_email(user.email, token)
        except Exception as e:
            logger.error(f"Failed to send password reset email for {user.email}", exc_info=True)

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        """
        O CAMINHO FICA SALVO AQUI!
        Executado quando o sistema solicita a verificação do e-mail do usuário.
        """
        _ = request
        logger.info(f"Mudança de status ou verificação solicitada para: {user.email}")
        
        # 🗺️ O caminho/link que o administrador vai clicar no e-mail:
        # Ele vai para a porta 3000 do Frontend Next.js passar o token!
        verify_url = f"{FRONTEND_URL}/verify-email?token={token}"
        
        logger.info(f"Link de verificação gerado para o admin: {verify_url}")
        
        # Aqui você chamaria o seu serviço de e-mail (Exemplo):
        # try:
        #     await send_verification_email(user.email, verify_url)
        # except Exception as e:
        #     logger.error(f"Falha ao enviar e-mail de verificação para {user.email}")


async def get_user_manager(user_db=Depends(get_user_db)):
    """
    Dependency to get the UserManager instance.
    """
    yield UserManager(user_db)