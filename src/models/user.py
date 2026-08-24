from __future__ import annotations
from typing import Optional, List
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Float, Integer, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from src.database.base import Base

class User(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "users"
    
    username: Mapped[str] = mapped_column(String(length=100), nullable=True)

    # Plano e Assinatura
    plan_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("plans.id"), nullable=True)
    plan = relationship("Plan", back_populates="users")
    plan_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Broker Principal (Legacy Support)
    broker: Mapped[Optional[str]] = mapped_column(String(length=50), default="iqoption")
    api_token: Mapped[Optional[str]] = mapped_column(String(length=255), nullable=True)

    # IQ Option Legacy
    iq_email: Mapped[Optional[str]] = mapped_column(String(length=255), nullable=True)
    iq_password: Mapped[Optional[str]] = mapped_column(String(length=255), nullable=True)

    # Configurações de Trade
    stake: Mapped[float] = mapped_column(Float, default=1.0)
    max_gales: Mapped[int] = mapped_column(Integer, default=6)
    risk_mode: Mapped[str] = mapped_column(String(20), default="safe")

    # Stats
    total_profit: Mapped[float] = mapped_column(Float, default=0.0)
    daily_stop_loss: Mapped[float] = mapped_column(Float, default=50.0)
    daily_meta: Mapped[float] = mapped_column(Float, default=10.0)

    # Gerenciamento de Ciclo / Martingale
    current_cycle_step: Mapped[int] = mapped_column(Integer, default=0)
    cycle_step: Mapped[int] = mapped_column(Integer, default=0)  # alias usado por ai_engine/plan_manager
    max_cycle_pct: Mapped[float] = mapped_column(Float, default=0.10)
    is_in_cycle: Mapped[bool] = mapped_column(Boolean, default=False)

    # Preferências do usuário
    stop_loss_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    daily_meta_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    telegram_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_protection: Mapped[bool] = mapped_column(Boolean, default=False)

    # Modo de Sinal: "telegram" ou "tradingview"
    signal_source: Mapped[str] = mapped_column(String(20), default="telegram")
    webhook_secret: Mapped[Optional[str]] = mapped_column("mt4_api_key", String(64), nullable=True)

    # Controle de Meta Diária (Auto-Lock)
    meta_hit_today: Mapped[bool] = mapped_column(Boolean, default=False)
    meta_hit_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD
    auto_lock_meta: Mapped[bool] = mapped_column(Boolean, default=False)

    # Controle Administrativo
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active_trading: Mapped[bool] = mapped_column(Boolean, default=True)
    trading_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    liberado: Mapped[bool] = mapped_column(Boolean, default=False)  # Admin precisa liberar
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Moeda de exibição (USD ou BRL)
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # ========================================
    # Link para Multi-Broker (NOVO)
    # ========================================
    broker_settings: Mapped[List["BrokerSetting"]] = relationship(
        "BrokerSetting",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"

    # ========================================
    # Métodos auxiliares para backwards compatibility
    # ========================================

    def get_primary_broker(self) -> Optional["BrokerSetting"]:
        """Retorna o broker principal do usuário."""
        from src.models.broker import BrokerSetting
        return next((bs for bs in self.broker_settings if bs.is_primary and bs.is_active), None)

    def get_all_active_brokers(self) -> List["BrokerSetting"]:
        """Retorna todos os brokers ativos."""
        return [bs for bs in self.broker_settings if bs.is_active]

    def get_total_balance(self) -> float:
        """Calcula saldo total em todos os brokers."""
        return sum(bs.balance or 0 for bs in self.get_all_active_brokers())

    def get_daily_total_profit(self) -> float:
        """Calcula lucro total do dia em todos os brokers."""
        return sum(bs.today_profit for bs in self.get_all_active_brokers())


class SignalUsage(Base):
    __tablename__ = "signal_usage"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    date: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    count: Mapped[int] = mapped_column(Integer, default=0)


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    max_signals_per_day: Mapped[int] = mapped_column(Integer, default=5)
    max_stake: Mapped[float] = mapped_column(Float, default=5.0)
    price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Brokers permitidos para este plano (lista de strings: iqoption, quotex, pocketoption, deriv)
    allowed_brokers: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    users = relationship("User", back_populates="plan")

    def get_allowed_brokers(self) -> List[str]:
        """Retorna lista de brokers permitidos para este plano."""
        import json
        if not self.allowed_brokers:
            return []
        try:
            return json.loads(self.allowed_brokers)
        except Exception:
            return []

    def get_allowed_brokers(self) -> List[str]:
        """Retorna lista de brokers permitidos para este plano."""
        if not self.allowed_brokers:
            return []
        import json
        try:
            return json.loads(self.allowed_brokers)
        except Exception:
            return []

    def set_allowed_brokers(self, brokers: List[str]) -> None:
        """Define lista de brokers permitidos."""
        import json
        self.allowed_brokers = json.dumps(brokers)


class PlanHistory(Base):
    __tablename__ = "plan_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    old_plan: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    new_plan: Mapped[str] = mapped_column(String(50))
    changed_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class AdminLog(Base):
    __tablename__ = "admin_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_email: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(100))
    target_user: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


# Importa no final do arquivo de forma segura para o SQLAlchemy resolver relacionamentos遅延
from src.models.broker import BrokerSetting