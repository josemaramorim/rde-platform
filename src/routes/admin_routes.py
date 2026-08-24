from __future__ import annotations

import uuid
import json
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.users import current_superuser
from src.models.user import User, Plan, PlanHistory, AdminLog
from src.database.session import get_async_session
from src.logger import log_admin

router = APIRouter(prefix="/admin/v2", tags=["Admin V2"])

@router.get("/users", response_model=List[dict])
async def list_users_enhanced(
    plan_filter: Optional[str] = None,
    only_active_package: bool = False,
    db: AsyncSession = Depends(get_async_session),
    admin: User = Depends(current_superuser),
):
    """
    Enhanced user list with online status and package tracking.
    """
    query = select(User).options(selectinload(User.plan))

    if plan_filter:
        query = query.join(Plan).where(Plan.name == plan_filter)

    if only_active_package:
        query = query.where(User.plan_id.isnot(None), User.plan_expires_at > datetime.utcnow())

    result = await db.execute(query)
    users = result.scalars().all()

    now = datetime.utcnow()

    def _plan_name(u: User) -> str:
        if u.plan and u.plan.name:
            return u.plan.name
        if u.plan_id:
            return f"Plano {u.plan_id}"
        return "Free"

    return [
        {
            "id": u.id,
            "email": u.email,
            "username": u.username,
            "is_active": u.is_active,
            "is_admin": u.is_admin,
            "is_superuser": u.is_superuser,
            "liberado": u.liberado,
            "trading_enabled": u.trading_enabled,
            "last_seen": u.last_seen,
            "is_online": bool(u.last_seen and (now - u.last_seen) < timedelta(minutes=5)),
            "plan_id": u.plan_id,
            "plan_name": _plan_name(u),
            "plan_expires_at": u.plan_expires_at,
            "has_active_package": (u.plan_expires_at and u.plan_expires_at > now),
            "total_profit": u.total_profit,
            "stake": u.stake,
            "risk_mode": u.risk_mode,
            "admin_notes": u.admin_notes,
        }
        for u in users
    ]

@router.patch("/user/{user_id}/control")
async def control_user(
    user_id: uuid.UUID,
    trading_enabled: Optional[bool] = None,
    stake: Optional[float] = None,
    risk_mode: Optional[str] = None,
    admin_notes: Optional[str] = None,
    db: AsyncSession = Depends(get_async_session),
    admin: User = Depends(current_superuser),
):
    """
    Update a user's trading settings and admin notes.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    changes = []
    if trading_enabled is not None:
        user.trading_enabled = trading_enabled
        changes.append(f"trading_enabled={trading_enabled}")
        
    if stake is not None:
        user.stake = stake
        changes.append(f"stake={stake}")
        
    if risk_mode is not None:
        user.risk_mode = risk_mode
        changes.append(f"risk_mode={risk_mode}")
        
    if admin_notes is not None:
        user.admin_notes = admin_notes
        changes.append("updated_notes")

    if changes:
        db.add(AdminLog(
            admin_email=admin.email,
            action="control_user",
            target_user=user.email,
            detail=", ".join(changes)
        ))
        await db.commit()
        log_admin(admin.email, "control_user", f"{user.email}: {', '.join(changes)}")

    return {"status": "success", "user_id": user_id, "changes": changes}

class PlanUpdate(BaseModel):
    plan_name: str


# Duração de cada plano em dias (Free anual, Pro 6 meses, VIP anual)
PLAN_DURATION_DAYS = {
    "free": 365,
    "pro": 180,
    "vip": 365,
}


@router.patch("/user/{user_id}/plan")
async def set_user_plan(
    user_id: uuid.UUID,
    payload: PlanUpdate,
    db: AsyncSession = Depends(get_async_session),
    admin: User = Depends(current_superuser),
):
    """
    Define o plano (Free / Pro / VIP) de um usuário, com validade conforme o plano:
    Free = 1 ano, Pro = 6 meses, VIP = 1 ano.
    """
    raw = (payload.plan_name or "").strip()
    key = raw.lower()

    result = await db.execute(select(Plan))
    plans = result.scalars().all()
    plan = next((p for p in plans if p.name and p.name.lower() == key), None)
    if not plan:
        valid = ", ".join(sorted({p.name for p in plans}))
        raise HTTPException(status_code=400, detail=f"Plano '{raw}' inválido. Use: {valid}.")

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.plan_id = plan.id
    days = PLAN_DURATION_DAYS.get(key, 365)
    user.plan_expires_at = datetime.utcnow() + timedelta(days=days)

    db.add(AdminLog(
        admin_email=admin.email,
        action="set_user_plan",
        target_user=user.email,
        detail=f"plan={plan.name}",
    ))
    await db.commit()
    log_admin(admin.email, "set_user_plan", f"{user.email}: {plan.name}")
    return {"status": "success", "plan_id": plan.id, "plan_name": plan.name}


@router.post("/user/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_session),
    admin: User = Depends(current_superuser),
):
    """
    Toggle a user's is_active status (block/unblock).
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = not user.is_active
    db.add(AdminLog(
        admin_email=admin.email,
        action="toggle_active",
        target_user=user.email,
        detail=f"is_active={user.is_active}"
    ))
    await db.commit()
    return {"status": "success", "is_active": user.is_active}


class PlanBrokersUpdate(BaseModel):
    plan_name: str
    allowed_brokers: List[str]  # ["iqoption", "quotex", ...]


@router.get("/plans/brokers")
async def list_plans_brokers(
    db: AsyncSession = Depends(get_async_session),
    admin: User = Depends(current_superuser),
):
    """Lista todos os planos e seus brokers permitidos."""
    result = await db.execute(select(Plan))
    plans = result.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "max_signals_per_day": p.max_signals_per_day,
            "max_stake": p.max_stake,
            "price_usd": p.price_usd,
            "is_demo": p.is_demo,
            "allowed_brokers": json.loads(p.allowed_brokers) if p.allowed_brokers else [],
        }
        for p in plans
    ]


@router.patch("/plans/brokers")
async def update_plan_brokers(
    payload: PlanBrokersUpdate,
    db: AsyncSession = Depends(get_async_session),
    admin: User = Depends(current_superuser),
):
    """Atualiza os brokers permitidos para um plano."""
    result = await db.execute(select(Plan).where(Plan.name.ilike(payload.plan_name)))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plano '{payload.plan_name}' não encontrado")

    valid = {"iqoption", "deriv"}
    for b in payload.allowed_brokers:
        if b.lower() not in valid:
            raise HTTPException(status_code=400, detail=f"Broker '{b}' inválido. Use: {', '.join(valid)}")

    plan.allowed_brokers = json.dumps([b.lower() for b in payload.allowed_brokers])
    db.add(plan)
    db.add(AdminLog(
        admin_email=admin.email,
        action="update_plan_brokers",
        target_user=None,
        detail=f"plan={plan.name}, brokers={plan.allowed_brokers}"
    ))
    await db.commit()
    log_admin(admin.email, "update_plan_brokers", f"{plan.name}: {plan.allowed_brokers}")
    return {"status": "success", "plan": plan.name, "allowed_brokers": json.loads(plan.allowed_brokers)}
