from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from src.database.session import get_async_session
from src.auth.users import current_active_user
from src.models.user import User
from src.models.broker import BrokerSetting
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/user", tags=["User Settings"])


class UserPreferences(BaseModel):
    stop_loss_pct: Optional[float] = None
    daily_meta_pct: Optional[float] = None
    telegram_enabled: Optional[bool] = None
    latency_protection: Optional[bool] = None
    stake: Optional[float] = None
    risk_mode: Optional[str] = None
    broker: Optional[str] = None
    auto_lock_meta: Optional[bool] = None
    signal_source: Optional[str] = None


@router.get("/preferences")
async def get_preferences(user: User = Depends(current_active_user)):
    return {
        "stop_loss_pct": user.stop_loss_pct,
        "daily_meta_pct": user.daily_meta_pct,
        "telegram_enabled": user.telegram_enabled,
        "latency_protection": user.latency_protection,
        "stake": user.stake,
        "risk_mode": user.risk_mode,
        "broker": user.broker,
        "auto_lock_meta": user.auto_lock_meta,
        "signal_source": user.signal_source or "telegram",
    }


@router.patch("/preferences")
async def update_preferences(
    prefs: UserPreferences,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    from sqlalchemy import select as sa_select

    # Save per-broker risk config to ALL active BrokerSettings (multi-broker)
    result = await db.execute(
        sa_select(BrokerSetting).where(
            BrokerSetting.user_id == user.id,
            BrokerSetting.is_active == True,
        )
    )
    active_settings = result.scalars().all()

    if active_settings:
        for active_setting in active_settings:
            if prefs.stop_loss_pct is not None:
                active_setting.stop_loss_pct = prefs.stop_loss_pct
            if prefs.daily_meta_pct is not None:
                active_setting.daily_meta_pct = prefs.daily_meta_pct
            if prefs.stake is not None:
                active_setting.stake = prefs.stake
            if prefs.auto_lock_meta is not None:
                active_setting.auto_lock_meta = prefs.auto_lock_meta
                if not prefs.auto_lock_meta:
                    active_setting.meta_hit_today = False
                    active_setting.meta_hit_date = None
            db.add(active_setting)

    # Also save user-level fields (shared across brokers)
    if prefs.telegram_enabled is not None:
        user.telegram_enabled = prefs.telegram_enabled
    if prefs.latency_protection is not None:
        user.latency_protection = prefs.latency_protection
    if prefs.risk_mode is not None:
        user.risk_mode = prefs.risk_mode
    if prefs.broker is not None:
        user.broker = prefs.broker
    if prefs.signal_source is not None:
        if prefs.signal_source in ("telegram", "tradingview"):
            user.signal_source = prefs.signal_source

    db.add(user)
    await db.commit()
    return {"status": "success"}


@router.get("/estado")
async def get_estado(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Retorna o estado completo do usuário — persiste entre abas e dispositivos.
    Frontend deve sempre buscar daqui ao carregar qualquer página.
    """
    import json
    result = await db.execute(
        select(User).options(
            selectinload(User.broker_settings),
            selectinload(User.plan),
        ).where(User.id == user.id)
    )
    u = result.scalar_one_or_none() or user
    active_broker = next((s for s in (u.broker_settings or []) if s.is_active), None) if u else None
    plan_name = u.plan.name.lower() if u.plan else "vip"
    is_demo = u.plan.is_demo if u.plan else True
    allowed_brokers = u.plan.get_allowed_brokers() if u.plan else []
    broker_balance = 0.0
    broker_connected = False
    broker_mode = "Demo" if is_demo else "Real"
    if active_broker:
        broker_connected = True
        broker_mode = "Demo" if active_broker.is_demo else "Real"
        if active_broker.balance:
            broker_balance = float(active_broker.balance)

    # Read per-broker risk config from active broker, fallback to user-level
    if active_broker:
        broker_stake = active_broker.stake
        broker_stop_loss_pct = active_broker.stop_loss_pct
        broker_daily_meta_pct = active_broker.daily_meta_pct
        broker_auto_lock_meta = active_broker.auto_lock_meta
        broker_meta_hit_today = active_broker.meta_hit_today
        broker_meta_hit_date = active_broker.meta_hit_date
    else:
        broker_stake = u.stake
        broker_stop_loss_pct = u.stop_loss_pct
        broker_daily_meta_pct = u.daily_meta_pct
        broker_auto_lock_meta = u.auto_lock_meta or False
        broker_meta_hit_today = u.meta_hit_today or False
        broker_meta_hit_date = u.meta_hit_date

    # Brokers permitidos pelo plano do usuário
    allowed_brokers = []
    if u.plan and u.plan.allowed_brokers:
        try:
            allowed_brokers = json.loads(u.plan.allowed_brokers)
        except Exception:
            allowed_brokers = []

    return {
        "email": u.email or "",
        "username": u.username or "",
        "liberado": u.liberado or u.is_admin,
        "is_admin": u.is_admin,
        "plan_name": plan_name,
        "plan_expires_at": u.plan_expires_at,
        "broker_ativo": active_broker.broker_name if active_broker else (u.broker or "iqoption"),
        "broker_is_demo": active_broker.is_demo if active_broker else is_demo,
        "stake": broker_stake,
        "risk_mode": u.risk_mode or "safe",
        "stop_loss_pct": broker_stop_loss_pct,
        "daily_meta_pct": broker_daily_meta_pct,
        "telegram_enabled": u.telegram_enabled,
        "latency_protection": u.latency_protection,
        "capital_planilha": u.total_profit if u.total_profit and u.total_profit > 0 else None,
        "broker_balance": broker_balance,
        "broker_mode": broker_mode,
        "broker_connected": broker_connected,
        "brokers_conectados": {},
        "auto_lock_meta": broker_auto_lock_meta,
        "meta_hit_today": broker_meta_hit_today,
        "meta_hit_date": broker_meta_hit_date,
        "signal_source": u.signal_source or "telegram",
        "webhook_secret": u.webhook_secret or None,
        "currency": (u.currency or "USD").upper(),
        "allowed_brokers": allowed_brokers,
    }


class CurrencyUpdate(BaseModel):
    currency: str


@router.patch("/currency")
async def update_currency(
    payload: CurrencyUpdate,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    cur = (payload.currency or "USD").upper()
    if cur not in ("USD", "BRL"):
        cur = "USD"
    user.currency = cur
    db.add(user)
    await db.commit()
    return {"status": "success", "currency": cur}


@router.post("/salvar-capital")
async def salvar_capital(
    capital: float,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Salva o capital atual da planilha no banco."""
    user.daily_meta = capital
    db.add(user)
    await db.commit()
    return {"status": "ok", "capital": capital}


@router.post("/salvar-broker-ativo")
async def salvar_broker_ativo(
    broker_name: str,
    is_demo: bool,
    balance: float,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """Salva o broker ativo e saldo no banco para persistir entre paginas."""
    from src.models.broker import BrokerSetting
    from sqlalchemy import select as sa_select

    # Ativar o escolhido sem desativar as demais (modo multi-broker)
    result = await db.execute(sa_select(BrokerSetting).where(BrokerSetting.user_id == user.id))
    all_settings = result.scalars().all()
    for s in all_settings:
        if s.broker_name == broker_name:
            s.is_active = True
            s.is_demo = is_demo
            s.balance = balance

    user.broker = broker_name
    db.add(user)
    await db.commit()
    return {"status": "ok", "broker": broker_name, "is_demo": is_demo, "balance": balance}
