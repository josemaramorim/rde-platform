from __future__ import annotations
import uuid
from datetime import datetime, date
from sqlalchemy import String, Boolean, Integer, ForeignKey, DateTime, Date, Float
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from src.database.base import Base


class PlanilhaProgress(Base):
    __tablename__ = "planilha_progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    day_number: Mapped[int] = mapped_column(Integer)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    capital_base: Mapped[float] = mapped_column(Float, default=0.0)
    daily_profit: Mapped[float] = mapped_column(Float, default=0.0)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    class Config:
        unique_together = ("user_id", "day_number")
