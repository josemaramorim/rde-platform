"""
Persistent WebSocket connection pool – one connection per api_token.
Suporta múltiplas corretoras: IQ Option, Quotex, Pocket Option
"""
import json
import threading
import logging
from typing import Dict, Optional, Tuple
from enum import Enum

try:
    import websocket
except ImportError:
    websocket = None

logger = logging.getLogger("rde")


class Broker(Enum):
    """Enum para diferentes corretoras."""
    IQOPTION = "iqoption"
    QUOTEX = "quotex"
    POCKETOPTION = "pocketoption"


class BrokerConfig:
    """Configuração específica de cada corretora."""
    
    CONFIGS = {
        Broker.IQOPTION: {
            "url": "wss://wsapi.iqoption.com/echo/websocket",
            "auth_method": "iqoption",
            "timeout": 15,
        },
        Broker.QUOTEX: {
            "url": "wss://api-tradings-qxweb.quotex.io",
            "auth_method": "quotex",
            "timeout": 15,
        },
        Broker.POCKETOPTION: {
            "url": "wss://wss.po.market/websocket",
            "auth_method": "pocketoption",
            "timeout": 15,
        }
    }
    
    @classmethod
    def get(cls, broker: Broker) -> Dict:
        """Obtém configuração da corretora."""
        return cls.CONFIGS.get(broker, {})


class IQOptionAuth:
    """Autenticação para IQ Option."""
    
    @staticmethod
    def build_auth_message(api_token: str) -> str:
        """Constrói mensagem de autenticação para IQ Option."""
        return json.dumps({
            "method": "authorize",
            "params": {
                "auth_token": api_token
            }
        })
    
    @staticmethod
    def verify_auth_response(response: Dict) -> Tuple[bool, Optional[str]]:
        """Verifica resposta de autenticação."""
        if response.get("isSuccessful"):
            return True, None
        error = response.get("message", "Unknown error")
        return False, error


class QuotexAuth:
    """Autenticação para Quotex."""
    
    @staticmethod
    def build_auth_message(api_token: str) -> str:
        """Constrói mensagem de autenticação para Quotex."""
        return json.dumps({
            "method": "authorize",
            "token": api_token
        })
    
    @staticmethod
    def verify_auth_response(response: Dict) -> Tuple[bool, Optional[str]]:
        """Verifica resposta de autenticação."""
        if response.get("status") == "success" or response.get("authorized"):
            return True, None
        error = response.get("message", "Authorization failed")
        return False, error


class PocketOptionAuth:
    """Autenticação para Pocket Option."""
    
    @staticmethod
    def build_auth_message(api_token: str) -> str:
        """Constrói mensagem de autenticação para Pocket Option."""
        return json.dumps({
            "method": "auth",
            "token": api_token
        })
    
    @staticmethod
    def verify_auth_response(response: Dict) -> Tuple[bool, Optional[str]]:
        """Verifica resposta de autenticação."""
        if response.get("success") or response.get("authenticated"):
            return True, None
        error = response.get("message", "Authentication failed")
        return False, error


# Mapeamento de métodos de autenticação
AUTH_HANDLERS = {
    "iqoption": IQOptionAuth,
    "quotex": QuotexAuth,
    "pocketoption": PocketOptionAuth,
}

# Pool de conexões: (broker, api_token) -> WebSocket
_connections: Dict[Tuple[Broker, str], object] = {}
_lock = threading.Lock()


def get_connection(api_token: str, broker: Broker = Broker.IQOPTION) -> object:
    """
    Retorna conexão existente ou cria uma nova.
    
    Args:
        api_token: Token de autenticação da corretora
        broker: Enum da corretora (padrão: IQOPTION)
    
    Returns:
        WebSocket connection object
    
    Raises:
        RuntimeError: Se websocket-client não está instalado
        ConnectionError: Se autenticação falhar
    """
    
    connection_key = (broker, api_token)
    
    with _lock:
        ws = _connections.get(connection_key)
        
        # Verifica se conexão existente está viva
        if ws is not None:
            try:
                ws.ping()
                return ws
            except Exception:
                logger.warning(
                    f"Dead WebSocket detected for {broker.value}, reconnecting…"
                )
                _connections.pop(connection_key, None)
        
        # Cria nova conexão
        if websocket is None:
            raise RuntimeError("websocket-client is not installed.")
        
        config = BrokerConfig.get(broker)
        ws_url = config["url"]
        timeout = config["timeout"]
        auth_method = config["auth_method"]
        
        # Estabelece conexão
        try:
            ws = websocket.create_connection(ws_url, timeout=timeout)
        except Exception as e:
            raise ConnectionError(f"Failed to connect to {broker.value}: {str(e)}")
        
        # Autentica
        auth_handler = AUTH_HANDLERS[auth_method]
        auth_message = auth_handler.build_auth_message(api_token)
        
        try:
            ws.send(auth_message)
            auth_resp_str = ws.recv()
            auth_resp = json.loads(auth_resp_str)
            
            success, error = auth_handler.verify_auth_response(auth_resp)
            
            if not success:
                ws.close()
                raise ConnectionError(
                    f"{broker.value} auth failed: {error}"
                )
            
            _connections[connection_key] = ws
            logger.info(
                f"New WebSocket connection established for {broker.value} "
                f"token …{api_token[-6:]}"
            )
            return ws
            
        except json.JSONDecodeError as e:
            ws.close()
            raise ConnectionError(
                f"Invalid JSON response from {broker.value}: {str(e)}"
            )
        except Exception as e:
            ws.close()
            raise ConnectionError(
                f"Authentication error on {broker.value}: {str(e)}"
            )


def close_connection(api_token: str, broker: Broker = Broker.IQOPTION):
    """
    Fecha uma conexão específica.
    
    Args:
        api_token: Token de autenticação
        broker: Enum da corretora
    """
    connection_key = (broker, api_token)
    
    with _lock:
        ws = _connections.pop(connection_key, None)
        if ws is not None:
            try:
                ws.close()
                logger.info(f"Connection closed for {broker.value}")
            except Exception as e:
                logger.warning(f"Error closing connection: {str(e)}")


def close_all_for_broker(broker: Broker):
    """
    Fecha todas as conexões de uma corretora.
    
    Args:
        broker: Enum da corretora
    """
    with _lock:
        keys_to_remove = [
            key for key in _connections.keys() if key[0] == broker
        ]
        for key in keys_to_remove:
            try:
                ws = _connections.pop(key)
                ws.close()
            except Exception as e:
                logger.warning(f"Error closing connection: {str(e)}")
        
        if keys_to_remove:
            logger.info(f"Closed {len(keys_to_remove)} connections for {broker.value}")


def close_all():
    """Fecha todas as conexões pooled (chamado no shutdown)."""
    with _lock:
        for ws in _connections.values():
            try:
                ws.close()
            except Exception:
                pass
        _connections.clear()
        logger.info("All WebSocket connections closed")


def get_pool_status() -> Dict:
    """Retorna status do pool de conexões."""
    with _lock:
        status = {}
        for (broker, token), ws in _connections.items():
            broker_name = broker.value
            if broker_name not in status:
                status[broker_name] = []
            status[broker_name].append(f"…{token[-6:]}")
        return status