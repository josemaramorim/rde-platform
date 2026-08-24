"""
Repository para BrokerSetting - Operações CRUD e consultas customizadas
"""

from typing import Optional, List
import uuid
from datetime import datetime
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.models.broker import BrokerSetting, BrokerConnection, BrokerTrade, BrokerType, BrokerStatus
from src.models.user import User


class BrokerSettingRepository:
    """Repository para gerenciar configurações de broker."""

    def __init__(self, db: Session):
        self.db = db

    # ========================
    # CRUD BÁSICO
    # ========================

    def create(
        self,
        user_id: uuid.UUID,
        broker_type: BrokerType,
        broker_name: str,
        api_token: Optional[str] = None,
        is_primary: bool = False,
        **kwargs
    ) -> BrokerSetting:
        """
        Cria nova configuração de broker.
        
        Args:
            user_id: ID do usuário
            broker_type: Tipo de broker (IQOPTION, QUOTEX, POCKETOPTION)
            broker_name: Nome amigável (ex: "IQ Principal")
            api_token: Token de autenticação
            is_primary: Define como broker principal
            **kwargs: Campos adicionais específicos do broker
        
        Returns:
            BrokerSetting criado
        """
        # Se é primary, desativa outras
        if is_primary:
            self.db.query(BrokerSetting).filter(
                and_(
                    BrokerSetting.user_id == user_id,
                    BrokerSetting.is_primary == True
                )
            ).update({"is_primary": False})

        broker_setting = BrokerSetting(
            user_id=user_id,
            broker_type=broker_type,
            broker_name=broker_name,
            api_token=api_token,
            is_primary=is_primary,
            **kwargs
        )

        try:
            self.db.add(broker_setting)
            self.db.commit()
            self.db.refresh(broker_setting)
            return broker_setting
        except IntegrityError:
            self.db.rollback()
            raise ValueError(f"Erro ao criar BrokerSetting para usuário {user_id}")

    def get_by_id(self, broker_setting_id: uuid.UUID) -> Optional[BrokerSetting]:
        """Obtém BrokerSetting por ID."""
        return self.db.query(BrokerSetting).filter(
            BrokerSetting.id == broker_setting_id
        ).first()

    def get_by_user(self, user_id: uuid.UUID, active_only: bool = True) -> List[BrokerSetting]:
        """
        Obtém todas as configurações de broker de um usuário.
        
        Args:
            user_id: ID do usuário
            active_only: Se True, retorna apenas configurações ativas
        """
        query = self.db.query(BrokerSetting).filter(
            BrokerSetting.user_id == user_id
        )
        
        if active_only:
            query = query.filter(BrokerSetting.is_active == True)
        
        return query.all()

    def get_primary(self, user_id: uuid.UUID) -> Optional[BrokerSetting]:
        """Obtém broker principal do usuário."""
        return self.db.query(BrokerSetting).filter(
            and_(
                BrokerSetting.user_id == user_id,
                BrokerSetting.is_primary == True,
                BrokerSetting.is_active == True
            )
        ).first()

    def get_by_broker_type(self, user_id: uuid.UUID, broker_type: BrokerType) -> Optional[BrokerSetting]:
        """Obtém configuração de um tipo específico de broker."""
        return self.db.query(BrokerSetting).filter(
            and_(
                BrokerSetting.user_id == user_id,
                BrokerSetting.broker_type == broker_type,
                BrokerSetting.is_active == True
            )
        ).first()

    def update(self, broker_setting_id: uuid.UUID, **kwargs) -> Optional[BrokerSetting]:
        """Atualiza BrokerSetting."""
        broker_setting = self.get_by_id(broker_setting_id)
        if not broker_setting:
            return None

        for key, value in kwargs.items():
            if hasattr(broker_setting, key) and value is not None:
                setattr(broker_setting, key, value)

        broker_setting.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(broker_setting)
        return broker_setting

    def delete(self, broker_setting_id: uuid.UUID, soft: bool = True) -> bool:
        """
        Deleta BrokerSetting.
        
        Args:
            broker_setting_id: ID a deletar
            soft: Se True, faz soft delete (marca deleted_at)
        """
        broker_setting = self.get_by_id(broker_setting_id)
        if not broker_setting:
            return False

        if soft:
            broker_setting.deleted_at = datetime.utcnow()
            broker_setting.is_active = False
            self.db.commit()
        else:
            self.db.delete(broker_setting)
            self.db.commit()

        return True

    # ========================
    # STATUS E CONEXÃO
    # ========================

    def update_status(
        self,
        broker_setting_id: uuid.UUID,
        status: BrokerStatus,
        error_message: Optional[str] = None
    ) -> Optional[BrokerSetting]:
        """Atualiza status da conexão."""
        broker_setting = self.get_by_id(broker_setting_id)
        if not broker_setting:
            return None

        broker_setting.status = status
        broker_setting.connection_error = error_message

        if status == BrokerStatus.CONNECTED:
            broker_setting.last_connected = datetime.utcnow()
            broker_setting.last_heartbeat = datetime.utcnow()

        self.db.commit()
        self.db.refresh(broker_setting)
        return broker_setting

    def update_heartbeat(self, broker_setting_id: uuid.UUID) -> bool:
        """Atualiza timestamp do último heartbeat."""
        broker_setting = self.get_by_id(broker_setting_id)
        if not broker_setting:
            return False

        broker_setting.last_heartbeat = datetime.utcnow()
        self.db.commit()
        return True

    def get_connected(self, user_id: uuid.UUID) -> List[BrokerSetting]:
        """Retorna brokers conectados e ativos."""
        return self.db.query(BrokerSetting).filter(
            and_(
                BrokerSetting.user_id == user_id,
                BrokerSetting.status == BrokerStatus.CONNECTED,
                BrokerSetting.is_active == True
            )
        ).all()

    # ========================
    # SALDO E ESTATÍSTICAS
    # ========================

    def update_balance(
        self,
        broker_setting_id: uuid.UUID,
        balance: float
    ) -> Optional[BrokerSetting]:
        """Atualiza saldo do broker."""
        broker_setting = self.get_by_id(broker_setting_id)
        if not broker_setting:
            return None

        broker_setting.balance = balance
        broker_setting.balance_updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(broker_setting)
        return broker_setting

    def add_trade_result(
        self,
        broker_setting_id: uuid.UUID,
        is_win: bool,
        profit: float
    ) -> Optional[BrokerSetting]:
        """Registra resultado de um trade."""
        broker_setting = self.get_by_id(broker_setting_id)
        if not broker_setting:
            return None

        broker_setting.add_trade_result(is_win, profit)
        self.db.commit()
        self.db.refresh(broker_setting)
        return broker_setting

    def reset_daily_stats(self, broker_setting_id: uuid.UUID) -> bool:
        """Reseta estatísticas do dia."""
        broker_setting = self.get_by_id(broker_setting_id)
        if not broker_setting:
            return False

        broker_setting.reset_daily_stats()
        self.db.commit()
        return True

    def reset_all_daily_stats(self, user_id: uuid.UUID) -> int:
        """Reseta estatísticas do dia para todos os brokers do usuário."""
        broker_settings = self.get_by_user(user_id, active_only=False)
        for broker_setting in broker_settings:
            broker_setting.reset_daily_stats()
        self.db.commit()
        return len(broker_settings)

    # ========================
    # CONSULTAS AVANÇADAS
    # ========================

    def get_stats_by_broker(self, user_id: uuid.UUID) -> dict:
        """Retorna estatísticas agregadas por broker."""
        broker_settings = self.get_by_user(user_id, active_only=False)
        
        stats = {}
        for bs in broker_settings:
            stats[bs.broker_type.value] = {
                "name": bs.broker_name,
                "status": bs.status.value,
                "balance": bs.balance,
                "total_trades": bs.total_trades,
                "total_wins": bs.total_wins,
                "total_losses": bs.total_losses,
                "total_profit": bs.total_profit,
                "win_rate": (bs.total_wins / bs.total_trades * 100) if bs.total_trades > 0 else 0,
                "today_trades": bs.today_trades,
                "today_profit": bs.today_profit,
            }
        
        return stats

    def get_total_balance(self, user_id: uuid.UUID) -> float:
        """Calcula saldo total em todos os brokers."""
        broker_settings = self.get_by_user(user_id, active_only=True)
        total = sum(bs.balance or 0 for bs in broker_settings)
        return total

    def get_daily_total_profit(self, user_id: uuid.UUID) -> float:
        """Calcula lucro total do dia em todos os brokers."""
        broker_settings = self.get_by_user(user_id, active_only=True)
        total = sum(bs.today_profit for bs in broker_settings)
        return total

    # ========================
    # GERENCIAMENTO DE PRIMARY
    # ========================

    def set_primary(self, broker_setting_id: uuid.UUID) -> bool:
        """Define broker como principal."""
        broker_setting = self.get_by_id(broker_setting_id)
        if not broker_setting:
            return False

        # Desativa outros
        self.db.query(BrokerSetting).filter(
            and_(
                BrokerSetting.user_id == broker_setting.user_id,
                BrokerSetting.is_primary == True
            )
        ).update({"is_primary": False})

        broker_setting.is_primary = True
        broker_setting.is_active = True
        self.db.commit()
        return True


class BrokerConnectionRepository:
    """Repository para histórico de conexões."""

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        broker_setting_id: uuid.UUID,
        status: BrokerStatus,
        connection_type: str = "websocket",
        **kwargs
    ) -> BrokerConnection:
        """Cria registro de conexão."""
        connection = BrokerConnection(
            broker_setting_id=broker_setting_id,
            status=status,
            connection_type=connection_type,
            **kwargs
        )
        self.db.add(connection)
        self.db.commit()
        self.db.refresh(connection)
        return connection

    def close_connection(self, connection_id: int) -> bool:
        """Marca conexão como fechada."""
        connection = self.db.query(BrokerConnection).filter(
            BrokerConnection.id == connection_id
        ).first()
        
        if not connection:
            return False

        connection.disconnected_at = datetime.utcnow()
        if connection.connected_at:
            duration = (connection.disconnected_at - connection.connected_at).total_seconds()
            connection.duration_seconds = int(duration)

        self.db.commit()
        return True


class BrokerTradeRepository:
    """Repository para histórico de trades."""

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        broker_setting_id: uuid.UUID,
        asset: str,
        direction: str,
        duration: int,
        amount: float,
        **kwargs
    ) -> BrokerTrade:
        """Cria registro de trade."""
        trade = BrokerTrade(
            broker_setting_id=broker_setting_id,
            asset=asset,
            direction=direction,
            duration=duration,
            amount=amount,
            **kwargs
        )
        self.db.add(trade)
        self.db.commit()
        self.db.refresh(trade)
        return trade

    def close_trade(
        self,
        trade_id: int,
        status: str,
        result: str,
        profit_loss: float,
        exit_price: Optional[float] = None
    ) -> bool:
        """Fecha um trade."""
        trade = self.db.query(BrokerTrade).filter(BrokerTrade.id == trade_id).first()
        if not trade:
            return False

        trade.status = status
        trade.result = result
        trade.profit_loss = profit_loss
        trade.exit_price = exit_price
        trade.closed_at = datetime.utcnow()
        self.db.commit()
        return True

    def get_by_broker(self, broker_setting_id: uuid.UUID, limit: int = 100) -> List[BrokerTrade]:
        """Obtém últimos trades de um broker."""
        return self.db.query(BrokerTrade).filter(
            BrokerTrade.broker_setting_id == broker_setting_id
        ).order_by(BrokerTrade.created_at.desc()).limit(limit).all()

    def get_today_trades(self, broker_setting_id: uuid.UUID) -> List[BrokerTrade]:
        """Obtém trades de hoje."""
        from sqlalchemy import func, cast, Date
        today = cast(func.now(), Date)
        
        return self.db.query(BrokerTrade).filter(
            and_(
                BrokerTrade.broker_setting_id == broker_setting_id,
                cast(BrokerTrade.created_at, Date) == today
            )
        ).order_by(BrokerTrade.created_at.desc()).all()