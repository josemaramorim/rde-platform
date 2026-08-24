from typing import Dict, Any
from src.app.services.brokers.deriv_connector import DerivConnector
from src.app.services.brokers.iqoption_connector import IQOptionConnector
from src.app.services.encryption_service import encryption_service
from src.app.models.broker import BrokerSetting
from sqlalchemy.orm import Session


class BrokerManager:
    """
    Orchestrates connection requests between the RDE Risk Engine 
    and the actual Broker Connectors.
    """

    async def place_order(self, db: Session, user_id: int, trade_params: Dict[str, Any]):
        # 1. Fetch active broker settings for user
        active_set = db.query(BrokerSetting).filter(
            BrokerSetting.user_id == user_id,
            BrokerSetting.is_active == True
        ).first()

        if not active_set:
            return {"status": "error", "message": "Nenhuma corretora configurada ou ativa."}

        # 2. Map broker to connector
        broker_name = active_set.broker_name

        try:
            if broker_name == "DERIV":
                # Decrypt token
                token = encryption_service.decrypt(active_set.api_token)
                connector = DerivConnector(token)
                return await connector.execute_trade(
                    symbol=trade_params.get("symbol", "R_100"),
                    amount=trade_params.get("amount", "10.0"),
                    direction=trade_params.get("direction", "UP"),
                    duration=trade_params.get("duration", 1)
                )

            elif broker_name == "IQ_OPTION":
                email = active_set.email
                password = encryption_service.decrypt(active_set.password)
                connector = IQOptionConnector(email, password)
                return await connector.execute_binary_trade(
                    symbol=trade_params.get("symbol", "EURUSD"),
                    amount=trade_params.get("amount", 10.0),
                    direction=trade_params.get("direction", "UP"),
                    duration=trade_params.get("duration", 1)
                )

            return {"status": "error", "message": f"Broker {broker_name} não suportado ainda."}

        except Exception as e:
            return {"status": "error", "message": f"Erro de conexão: {str(e)}"}

    async def get_history(self, db: Session, user_id: int, limit: int = 10):
        active_set = db.query(BrokerSetting).filter(
            BrokerSetting.user_id == user_id,
            BrokerSetting.is_active == True
        ).first()

        if not active_set:
            return []

        broker_name = active_set.broker_name

        try:
            if broker_name == "DERIV":
                token = encryption_service.decrypt(active_set.api_token)
                connector = DerivConnector(token)
                return await connector.get_history(limit=limit)

            elif broker_name == "IQ_OPTION":
                email = active_set.email
                password = encryption_service.decrypt(active_set.password)
                connector = IQOptionConnector(email, password)
                return await connector.get_history(limit=limit)

            return []
        except Exception:
            return []


broker_manager = BrokerManager()
