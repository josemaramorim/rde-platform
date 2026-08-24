from __future__ import annotations
from typing import Optional, List
import uuid
from datetime import datetime, timedelta
import secrets
import string
from sqlalchemy import String, Boolean, Integer, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from src.database.base import Base


class TokenLicenca(Base):
    """Token de licença para distribuição controlada da plataforma."""
    __tablename__ = "token_licencas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    plano: Mapped[str] = mapped_column(String(50), nullable=False)  # Basic, Pro, VIP
    expiracao_dias: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    # Controle
    criado_por: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Uso
    usado_por: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    usuario: Mapped[Optional["User"]] = relationship("User", foreign_keys=[usado_por])
    usado_em: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Destinatário (email do cliente para quem o token foi gerado)
    destinatario: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Revogação
    revogado: Mapped[bool] = mapped_column(Boolean, default=False)
    revogado_em: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revogado_por: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Rastreamento do cliente
    ultimo_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    ultimo_user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ultima_atividade: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    @staticmethod
    def gerar_codigo(tamanho: int = 24) -> str:
        """Gera um token alfanumérico seguro."""
        alfabeto = string.ascii_uppercase + string.digits
        return ''.join(secrets.choice(alfabeto) for _ in range(tamanho))

    @property
    def expira_em(self) -> Optional[datetime]:
        """Data de expiração do token (baseada no uso)."""
        if self.usado_em:
            return self.usado_em + timedelta(days=self.expiracao_dias)
        return None

    @property
    def expirado(self) -> bool:
        """Verifica se o token já expirou."""
        if self.expira_em and datetime.utcnow() > self.expira_em:
            return True
        return False

    @property
    def disponivel(self) -> bool:
        """Token disponível para uso."""
        return not self.usado_por and not self.revogado

    @property
    def status(self) -> str:
        if self.revogado:
            return "revogado"
        if not self.usado_por:
            return "disponivel"
        if self.expirado:
            return "expirado"
        return "ativo"

    def __repr__(self) -> str:
        return f"<TokenLicenca {self.codigo[:12]}... [{self.status}]>"
