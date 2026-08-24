from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database.session import get_async_session
from src.auth.users import current_active_user
from src.models.user import User
from src.app.services.encryption_service import encryption_service
from src.models.broker import BrokerSetting
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/broker", tags=["broker"])


class BrokerCreate(BaseModel):
    broker_name: str
    api_token: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    is_demo: bool = True


@router.post("/settings")
async def save_broker_settings(
    settings: BrokerCreate, 
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user)
):
    # Check if exists
    query = select(BrokerSetting).where(
        BrokerSetting.user_id == user.id,
        BrokerSetting.broker_name == settings.broker_name
    )
    result = await db.execute(query)
    existing = result.scalar_one_or_none()

    # Encrypt sensitive data
    enc_token = encryption_service.encrypt(
        settings.api_token) if settings.api_token else None
    enc_pass = encryption_service.encrypt(
        settings.password) if settings.password else None

    # Comportamento Otimizado para Múltiplas Corretoras
    # Apenas DESATIVA as outras corretoras se esta for a PRIMEIRA configuração do usuário
    # e se as outras corretoras já estiverem ATIVAS. Evita conflitos entre corretoras.
    
    # Consulta todas as corretoras do usuário
    all_query = select(BrokerSetting).where(BrokerSetting.user_id == user.id)
    all_result = await db.execute(all_query)
    all_settings = all_result.scalars().all()
    
    if not existing:
        # Esta é a PRIMEIRA configuração do usuário - desativa todas as outras automaticamente
        # para manter o comportamento original e evitar estados inconsistentes
        for s in all_settings:
            if s.broker_name != settings.broker_name:
                s.is_active = False

    # Se esta corretora já existe e está sendo ATUALIZADA, manter o estado is_active existente
    if existing:
        # Preserva o estado de ativação existente
        settings.is_active = existing.is_active
    else:
        # Para NOVA configuração, definir como ativo por padrão
        settings.is_active = True

    if existing:
        existing.api_token = enc_token
        existing.email = settings.email
        existing.password = enc_pass
        existing.is_demo = settings.is_demo
        # Manter o estado is_active existente para configurações anteriores
    else:
        new_setting = BrokerSetting(
            user_id=user.id,
            broker_name=settings.broker_name,
            api_token=enc_token,
            email=settings.email,
            password=enc_pass,
            is_demo=settings.is_demo,
            is_active=settings.is_active
        )
        db.add(new_setting)

    await db.commit()
    return {"status": "success", "message": f"Settings for {settings.broker_name} saved securely."}


@router.get("/status")
async def get_broker_status(
    db: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user)
):
    query = select(BrokerSetting).where(BrokerSetting.user_id == user.id)
    result = await db.execute(query)
    settings = result.scalars().all()

    return [
        {
            "broker": s.broker_name,
            "is_active": s.is_active,
            "is_demo": s.is_demo,
            "has_token": s.api_token is not None,
            "has_email": s.email is not None
        } for s in settings
    ]
