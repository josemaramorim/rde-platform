from __future__ import annotations
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from typing import Optional
from src.database.session import get_async_session
from src.auth.users import current_active_user
from src.models.user import User
from src.models.planilha import PlanilhaProgress

router = APIRouter(prefix="/planilha", tags=["Planilha"])


class ProgressItem(BaseModel):
    day_number: int
    completed: bool
    capital_base: float = 0.0
    daily_profit: float = 0.0


class MarkDayRequest(BaseModel):
    day_number: int
    completed: bool = True
    capital_base: float = 0.0
    daily_profit: float = 0.0


@router.get("/progress")
async def get_progress(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    result = await db.execute(
        select(PlanilhaProgress).where(
            PlanilhaProgress.user_id == user.id
        ).order_by(PlanilhaProgress.day_number)
    )
    rows = result.scalars().all()
    return {
        "progress": {
            str(r.day_number): {
                "completed": r.completed,
                "capital_base": r.capital_base,
                "daily_profit": r.daily_profit,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in rows
        }
    }


@router.post("/mark-day")
async def mark_day(
    req: MarkDayRequest,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    result = await db.execute(
        select(PlanilhaProgress).where(
            and_(
                PlanilhaProgress.user_id == user.id,
                PlanilhaProgress.day_number == req.day_number,
            )
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.completed = req.completed
        existing.capital_base = req.capital_base
        existing.daily_profit = req.daily_profit
        existing.completed_at = datetime.utcnow() if req.completed else None
        db.add(existing)
    else:
        record = PlanilhaProgress(
            user_id=user.id,
            day_number=req.day_number,
            completed=req.completed,
            capital_base=req.capital_base,
            daily_profit=req.daily_profit,
            completed_at=datetime.utcnow() if req.completed else None,
        )
        db.add(record)

    await db.commit()
    return {"status": "ok", "day": req.day_number, "completed": req.completed}


@router.post("/auto-mark")
async def auto_mark_day(
    day_number: int,
    capital_base: float,
    daily_profit: float,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Marca dia automaticamente quando meta e atingida (chamado pelo copier)."""
    result = await db.execute(
        select(PlanilhaProgress).where(
            and_(
                PlanilhaProgress.user_id == user.id,
                PlanilhaProgress.day_number == day_number,
            )
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        if not existing.completed:
            existing.completed = True
            existing.capital_base = capital_base
            existing.daily_profit = daily_profit
            existing.completed_at = datetime.utcnow()
            db.add(existing)
    else:
        record = PlanilhaProgress(
            user_id=user.id,
            day_number=day_number,
            completed=True,
            capital_base=capital_base,
            daily_profit=daily_profit,
            completed_at=datetime.utcnow(),
        )
        db.add(record)

    await db.commit()
    return {"status": "ok", "day": day_number, "auto_marked": True}
