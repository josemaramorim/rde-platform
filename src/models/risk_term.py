from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from src.database.base import Base


class RiskTermAcceptance(Base):
    __tablename__ = "risk_term_acceptance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    email_confirmed: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    cpf_or_id: Mapped[str] = mapped_column(String(50))
    ip_address: Mapped[str] = mapped_column(String(50), default="")
    user_agent: Mapped[str] = mapped_column(Text, default="")
    term_version: Mapped[str] = mapped_column(String(20), default="1.0")
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    declined_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
