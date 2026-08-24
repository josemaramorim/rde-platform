# Re-export the canonical BrokerSetting model to avoid duplicate mapper conflict
from src.models.broker import BrokerSetting

__all__ = ["BrokerSetting"]
