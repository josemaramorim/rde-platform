"""
Audit Service — RDE Platform
Registra trades e conexoes na tabela broker_trades / broker_connections
para auditoria, historico e compliance.
"""
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("rde-audit")


def log_trade(
    user_id,
    broker_setting_id,
    symbol: str,
    direction: str,
    stake: float,
    duration: int,
    status: str = "pending",
    result: Optional[str] = None,
    profit_loss: Optional[float] = None,
    broker_trade_id: Optional[str] = None,
    is_martingale: bool = False,
    cycle_step: int = 0,
    notes: Optional[str] = None,
) -> Optional[int]:
    """Registra um trade na tabela broker_trades. Retorna o ID ou None em caso de erro."""
    try:
        from src.database.session import SessionLocal
        from src.models.broker import BrokerTrade

        db = SessionLocal()
        try:
            trade = BrokerTrade(
                broker_setting_id=broker_setting_id,
                broker_trade_id=broker_trade_id,
                asset=symbol,
                direction=direction,
                duration=duration,
                amount=stake,
                status=status,
                result=result,
                profit_loss=profit_loss,
                opened_at=datetime.utcnow(),
                is_martingale=is_martingale,
                cycle_step=cycle_step,
                notes=notes,
            )
            db.add(trade)
            db.commit()
            trade_id = trade.id
            logger.info(
                f"[AUDIT] Trade registrado: id={trade_id} {symbol} {direction} "
                f"${stake:.2f} status={status} result={result} profit={profit_loss}"
            )
            return trade_id
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[AUDIT] Falha ao registrar trade: {e}")
        return None


def update_trade_result(
    trade_id: int,
    status: str,
    result: Optional[str] = None,
    profit_loss: Optional[float] = None,
    balance_after: Optional[float] = None,
) -> bool:
    """Atualiza o resultado de um trade existente."""
    try:
        from src.database.session import SessionLocal
        from src.models.broker import BrokerTrade

        db = SessionLocal()
        try:
            trade = db.query(BrokerTrade).filter(BrokerTrade.id == trade_id).first()
            if not trade:
                return False
            trade.status = status
            trade.result = result
            trade.profit_loss = profit_loss
            trade.closed_at = datetime.utcnow()
            if balance_after is not None:
                trade.notes = f"{(trade.notes or '')} balance_after={balance_after:.2f}"
            db.commit()
            logger.info(
                f"[AUDIT] Trade atualizado: id={trade_id} status={status} "
                f"result={result} profit={profit_loss}"
            )
            return True
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[AUDIT] Falha ao atualizar trade {trade_id}: {e}")
        return False


def log_connection(
    broker_setting_id,
    status: str = "connected",
    connection_type: str = "websocket",
    error_message: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> Optional[int]:
    """Registra uma conexao na tabela broker_connections."""
    try:
        from src.database.session import SessionLocal
        from src.models.broker import BrokerConnection

        db = SessionLocal()
        try:
            conn = BrokerConnection(
                broker_setting_id=broker_setting_id,
                status=status,
                connection_type=connection_type,
                error_message=error_message,
                ip_address=ip_address,
                connected_at=datetime.utcnow(),
            )
            db.add(conn)
            db.commit()
            return conn.id
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[AUDIT] Falha ao registrar conexao: {e}")
        return None


def get_trades_today(user_id=None, broker_setting_id=None, limit: int = 50) -> list:
    """Retorna trades de hoje para o dashboard/auditoria."""
    try:
        from src.database.session import SessionLocal
        from src.models.broker import BrokerTrade

        db = SessionLocal()
        try:
            q = db.query(BrokerTrade)
            if broker_setting_id:
                q = q.filter(BrokerTrade.broker_setting_id == broker_setting_id)
            today = datetime.utcnow().strftime("%Y-%m-%d")
            trades = (
                q.filter(BrokerTrade.created_at >= today)
                .order_by(BrokerTrade.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": t.id,
                    "asset": t.asset,
                    "direction": t.direction,
                    "amount": t.amount,
                    "status": t.status,
                    "result": t.result,
                    "profit_loss": t.profit_loss,
                    "is_martingale": t.is_martingale,
                    "cycle_step": t.cycle_step,
                    "time": t.created_at.strftime("%H:%M:%S") if t.created_at else None,
                    "date": t.created_at.strftime("%Y-%m-%d") if t.created_at else None,
                }
                for t in trades
            ]
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[AUDIT] Falha ao buscar trades: {e}")
        return []


def get_trade_summary(user_id=None) -> dict:
    """Retorna resumo de trades de hoje."""
    try:
        from src.database.session import SessionLocal
        from src.models.broker import BrokerTrade
        from sqlalchemy import func

        db = SessionLocal()
        try:
            today = datetime.utcnow().strftime("%Y-%m-%d")
            q = db.query(BrokerTrade).filter(BrokerTrade.created_at >= today)

            total = q.count()
            wins = q.filter(BrokerTrade.result == "won").count()
            losses = q.filter(BrokerTrade.result == "lost").count()
            pending = q.filter(BrokerTrade.status == "pending").count()

            total_profit = (
                db.query(func.sum(BrokerTrade.profit_loss))
                .filter(BrokerTrade.created_at >= today, BrokerTrade.profit_loss.isnot(None))
                .scalar()
                or 0.0
            )

            return {
                "total_trades": total,
                "wins": wins,
                "losses": losses,
                "pending": pending,
                "win_rate": round((wins / total * 100) if total > 0 else 0, 1),
                "total_profit": round(float(total_profit), 2),
            }
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[AUDIT] Falha ao gerar resumo: {e}")
        return {"total_trades": 0, "wins": 0, "losses": 0, "pending": 0, "win_rate": 0, "total_profit": 0}
