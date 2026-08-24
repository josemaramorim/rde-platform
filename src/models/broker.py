"""
Modelo BrokerSetting - Gerencia múltiplos brokers por usuário
Suporta: IQ Option, Quotex, Pocket Option
"""

from __future__ import annotations
from typing import TYPE_CHECKING, List, Optional
from enum import Enum
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Float, Integer, ForeignKey, DateTime, Text, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from src.database.base import Base

if TYPE_CHECKING:
    from src.models.user import User
class BrokerType(str, Enum):
    """Tipos de brokers suportados."""
    IQOPTION = "iqoption"
    QUOTEX = "quotex"
    POCKETOPTION = "pocketoption"
    DERIV = "deriv"


class BrokerStatus(str, Enum):
    """Status da conexão com broker."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    INACTIVE = "inactive"


class BrokerSetting(Base):
    """
    Configurações específicas de cada broker por usuário.
    Um usuário pode ter múltiplas contas em diferentes brokers.
    """
    __tablename__ = "broker_settings"

    # Identificadores
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Relacionamento com User
    user: Mapped["User"] = relationship("User", back_populates="broker_settings")

    # Informações Básicas
    broker_type: Mapped[BrokerType] = mapped_column(SQLEnum(BrokerType, values_callable=lambda x: [e.value for e in x]), nullable=False, index=True)
    broker_name: Mapped[str] = mapped_column(String(50), nullable=False)  # Nome amigável ex: "IQ Principal"
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)  # Broker padrão do usuário
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    # Status e Conexão
    status: Mapped[BrokerStatus] = mapped_column(
        SQLEnum(BrokerStatus, values_callable=lambda x: [e.value for e in x]), 
        default=BrokerStatus.DISCONNECTED,
        index=True
    )
    last_connected: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    connection_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ========================
    # AUTENTICAÇÃO (Criptografada em produção)
    # ========================

    # Token/API Key (genérico - usar para todos os brokers)
    api_token: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # IQ Option Específico
    iq_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    iq_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    iq_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Quotex Específico
    quotex_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    quotex_api_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Pocket Option Específico
    po_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    po_api_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Deriv Específico (nova API: app_id da aplicação que gerou o PAT)
    deriv_app_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default="16929")
    deriv_token_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # validade do PAT (alertar 90d antes)

    # ========================
    # CONFIGURAÇÕES DE TRADE
    # ========================

    # Valores padrão (herdam ou sobrescrevem do User)
    default_stake: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Se None, usa User.stake
    max_stake: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_gales: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Stop Loss e Metas
    daily_stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    daily_meta: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Config de risco (percentuais, auto-lock, meta hit — por broker)
    stop_loss_pct: Mapped[float] = mapped_column(Float, default=5.0)
    daily_meta_pct: Mapped[float] = mapped_column(Float, default=3.0)
    stake: Mapped[float] = mapped_column(Float, default=1.0)
    auto_lock_meta: Mapped[bool] = mapped_column(Boolean, default=False)
    meta_hit_today: Mapped[bool] = mapped_column(Boolean, default=False)
    meta_hit_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Ciclos/Martingale
    max_cycle_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Proteção
    latency_protection: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_stop_on_loss: Mapped[bool] = mapped_column(Boolean, default=True)

    # ========================
    # SALDO E ESTATÍSTICAS
    # ========================

    balance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Saldo atual
    balance_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    total_wins: Mapped[int] = mapped_column(Integer, default=0)
    total_losses: Mapped[int] = mapped_column(Integer, default=0)
    total_profit: Mapped[float] = mapped_column(Float, default=0.0)
    
    today_trades: Mapped[int] = mapped_column(Integer, default=0)
    today_profit: Mapped[float] = mapped_column(Float, default=0.0)

    # ========================
    # RASTREAMENTO
    # ========================

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # Soft delete

    # Notas do Admin
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ========================
    # MÉTODOS AUXILIARES
    # ========================

    def __repr__(self) -> str:
        return f"<BrokerSetting {self.broker_name} ({self.broker_type.value})>"

    def is_connected(self) -> bool:
        """Verifica se está conectado."""
        return self.status == BrokerStatus.CONNECTED and self.is_active

    def is_configured(self) -> bool:
        """Verifica se tem credenciais configuradas."""
        if self.broker_type == BrokerType.IQOPTION:
            return bool(self.api_token or (self.iq_email and self.iq_password))
        elif self.broker_type == BrokerType.QUOTEX:
            return bool(self.api_token or self.quotex_api_key)
        elif self.broker_type == BrokerType.POCKETOPTION:
            return bool(self.api_token or self.po_api_key)
        return False

    def get_credentials(self) -> dict:
        """Retorna credenciais formatadas para o broker específico."""
        creds = {
            "broker_type": self.broker_type.value,
            "api_token": self.api_token,
        }

        if self.broker_type == BrokerType.IQOPTION:
            creds.update({
                "email": self.iq_email,
                "password": self.iq_password,
                "user_id": self.iq_user_id,
            })
        elif self.broker_type == BrokerType.QUOTEX:
            creds.update({
                "username": self.quotex_username,
                "api_key": self.quotex_api_key,
            })
        elif self.broker_type == BrokerType.POCKETOPTION:
            creds.update({
                "username": self.po_username,
                "api_key": self.po_api_key,
            })
        elif self.broker_type == BrokerType.DERIV:
            creds.update({
                "app_id": self.deriv_app_id or "16929",
            })

        return creds

    def get_trade_config(self) -> dict:
        """Retorna configurações de trade, usando defaults do User se não definido."""
        user = self.user
        
        return {
            "stake": self.stake or user.stake,
            "max_stake": self.max_stake or float('inf'),
            "max_gales": self.max_gales or user.max_gales,
            "daily_stop_loss": self.daily_stop_loss or user.daily_stop_loss,
            "daily_meta": self.daily_meta or user.daily_meta,
            "max_cycle_pct": self.max_cycle_pct or user.max_cycle_pct,
            "latency_protection": self.latency_protection,
            "stop_loss_pct": self.stop_loss_pct,
            "daily_meta_pct": self.daily_meta_pct,
            "auto_lock_meta": self.auto_lock_meta,
            "meta_hit_today": self.meta_hit_today,
        }

    def update_balance(self, balance: float, timestamp: Optional[datetime] = None):
        """Atualiza saldo do broker."""
        self.balance = balance
        self.balance_updated_at = timestamp or datetime.utcnow()

    def add_trade_result(self, is_win: bool, profit: float):
        """Registra resultado de um trade."""
        self.total_trades += 1
        if is_win:
            self.total_wins += 1
        else:
            self.total_losses += 1
        self.total_profit += profit
        self.today_trades += 1
        self.today_profit += profit

    def reset_daily_stats(self):
        """Reseta estatísticas do dia (chamado diariamente)."""
        self.today_trades = 0
        self.today_profit = 0.0


class BrokerConnection(Base):
    """
    Histórico e logs de conexões com brokers.
    Útil para debugging e auditoria.
    """
    __tablename__ = "broker_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    broker_setting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("broker_settings.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # Relacionamento
    broker_setting: Mapped[BrokerSetting] = relationship("BrokerSetting")

    # Informações da Conexão
    status: Mapped[BrokerStatus] = mapped_column(SQLEnum(BrokerStatus), nullable=False)
    connected_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    disconnected_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Detalhes
    connection_type: Mapped[str] = mapped_column(String(50))  # websocket, api, etc
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    def __repr__(self) -> str:
        return f"<BrokerConnection {self.status.value} at {self.connected_at}>"


class BrokerTrade(Base):
    """
    Histórico detalhado de trades por broker.
    Cada trade é rastreado aqui para análise e compliance.
    """
    __tablename__ = "broker_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    broker_setting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("broker_settings.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # Relacionamento
    broker_setting: Mapped[BrokerSetting] = relationship("BrokerSetting")

    # Identificadores do Trade
    broker_trade_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # ID no broker
    asset: Mapped[str] = mapped_column(String(20), nullable=False)  # EUR/USD, BTC/USD, etc
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # call, put
    duration: Mapped[int] = mapped_column(Integer, nullable=False)  # segundos

    # Valores
    amount: Mapped[float] = mapped_column(Float, nullable=False)  # valor da aposta
    entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    profit_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, won, lost, cancelled
    result: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # win, loss

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Metadata
    is_martingale: Mapped[bool] = mapped_column(Boolean, default=False)
    cycle_step: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<BrokerTrade {self.asset} {self.direction} {self.status}>"


# Importar User no final para evitar circular imports
from src.models.user import User