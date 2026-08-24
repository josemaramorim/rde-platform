"""
Pocket Option broker adapter for RDE Platform.

Uses the pocketoptionapi-async package (pip install).
Authentication is via SSID (session token extracted from browser DevTools).

SSID Format: 42["auth",{"session":"...","isDemo":1,"uid":12345,"platform":1}]

Unlike Deriv/IQ Option, this API is fully async, so we provide both
sync wrappers (for the Celery executor) and native async methods
(for the Telegram copier).
"""
import logging
from src.broker.base import BaseBroker
from src.broker._utils import run_async

try:
    from pocketoptionapi_async import (
        AsyncPocketOptionClient,
        OrderDirection,
    )
except ImportError:
    AsyncPocketOptionClient = None
    OrderDirection = None

logger = logging.getLogger("rde")


class PocketOptionBroker(BaseBroker):
    """
    PocketOption broker adapter.

    Args:
        ssid: The full SSID authentication string from browser DevTools.
              Format: 42["auth",{"session":"...","isDemo":1,"uid":...,"platform":1}]
        is_demo: Whether to operate in demo mode (True) or real mode (False).
    """

    def __init__(self, ssid: str, is_demo: bool = True):
        if AsyncPocketOptionClient is None:
            raise RuntimeError(
                "pocketoptionapi-async is not installed.\n"
                "Install with:\n"
                '  pip install pocketoptionapi-async'
            )
        self.ssid = ssid
        self.is_demo = is_demo
        self.client = None

    # ── Sync wrappers (for Celery / executor) ─────────────────────────

    def connect(self):
        """Synchronous connect wrapper."""
        run_async(self.async_connect())

    def send_order(self, symbol: str, stake: float, direction: str, duration: int = 1) -> dict:
        """Synchronous order placement."""
        return run_async(self.async_send_order(symbol, stake, direction, duration))

    def get_contract_status(self, order_id: str) -> str:
        """Sync wrapper to check if order won or lost."""
        return run_async(self.async_get_contract_status(order_id))

    def get_balance(self) -> float:
        """Sync wrapper to get account balance."""
        return run_async(self.async_get_balance())

    def disconnect(self):
        """Sync disconnect."""
        if self.client:
            try:
                run_async(self.client.disconnect())
            except Exception:
                pass
            self.client = None

    def _ensure_connected(self) -> bool:
        """Verifica se a conexao esta viva. Reconecta se necessario."""
        try:
            if self.client is None:
                self.connect()
                return True
            return True
        except Exception as e:
            logger.warning(f"Conexao Pocket Option perdida ({e}). Reconectando...")
            try:
                self.connect()
                return True
            except Exception as e2:
                logger.error(f"Falha ao reconectar Pocket Option: {e2}")
                return False

    async def _ensure_connected_async(self) -> bool:
        """Versao async do ensure_connected."""
        try:
            if self.client is None:
                await self.async_connect()
                return True
            bal = await self.client.get_balance()
            if bal is None:
                raise ConnectionError("Balance check returned None")
            return True
        except Exception as e:
            logger.warning(f"Conexao Pocket Option perdida ({e}). Reconectando...")
            try:
                await self.async_connect()
                return True
            except Exception as e2:
                logger.error(f"Falha ao reconectar Pocket Option: {e2}")
                return False

    # ── Async methods (native — for Telegram copier) ──────────────────

    async def async_connect(self):
        """Async connect — preferred method for async contexts."""
        ssid = self.ssid
        # Se vier o frame completo 42["auth",...], extrair apenas o session
        if ssid.startswith('42['):
            import json, re
            m = re.search(r'"session"\s*:\s*"((?:[^"\\]|\\.)*)"', ssid)
            if m:
                ssid = m.group(1)
        # Montar o frame completo no formato correto
        import json
        frame = json.dumps(["auth", {
            "session": ssid,
            "isDemo": 1 if self.is_demo else 0,
            "uid": 0,
            "platform": 2,
            "isFastHistory": True,
            "isOptimized": True
        }])
        ssid_final = f"42{frame}"
        
        self.client = AsyncPocketOptionClient(
            ssid=ssid_final,
            is_demo=self.is_demo,
            enable_logging=True,
        )
        connected = await self.client.connect()
        if not connected:
            raise ConnectionError(
                "Pocket Option: Connection failed. "
                "Check if SSID is valid and not expired."
            )
        logger.info(
            f"PocketOption connected ({'Demo' if self.is_demo else 'Real'})"
        )

    async def async_send_order(
        self, symbol: str, stake: float, direction: str, duration: int = 1
    ) -> dict:
        """
        Async order placement.
        direction: 'CALL' or 'PUT'
        duration: in minutes (1 for M1, 5 for M5, etc.)
        """
        if not await self._ensure_connected_async():
            return {"status": "error", "result": "Falha ao reconectar Pocket Option"}

        try:
            dir_enum = (
                OrderDirection.CALL
                if direction.upper() == "CALL"
                else OrderDirection.PUT
            )

            order = await self.client.place_order(
                asset=symbol,
                amount=stake,
                direction=dir_enum,
                duration=duration * 60,
            )

            logger.info(
                f"PO order: {order.order_id} | "
                f"{direction} {symbol} ${stake}"
            )

            return {
                "status": "ok",
                "result": "Ordem enviada com sucesso",
                "order_id": order.order_id,
            }
        except Exception as e:
            logger.error(f"Pocket Option order error for {symbol}: {e}")
            return {"status": "error", "result": str(e)}

    async def async_get_contract_status(self, order_id: str) -> str:
        """Async check for order result: 'won', 'lost', or 'error'."""
        try:
            # Try check_win first (waits for result)
            result = await self.client.check_win(order_id)
            if result is None:
                # Fallback to check_order_result
                result = await self.client.check_order_result(order_id)

            if result is None:
                return "error"

            # OrderResult has a .status field (OrderStatus enum)
            if hasattr(result, "status"):
                status_str = str(result.status).lower()
                if "win" in status_str:
                    return "won"
                elif "lose" in status_str or "loss" in status_str:
                    return "lost"

            # Simple bool/string fallback
            if result is True or result == "win":
                return "won"
            return "lost"

        except Exception as e:
            logger.error(f"❌ PO status check error: {e}")
            return "error"

    async def async_get_balance(self) -> float:
        """Async get balance."""
        try:
            balance = await self.client.get_balance()
            return balance.balance
        except Exception as e:
            logger.error(f"❌ PO balance error: {e}")
            return 0.0

    async def async_disconnect(self):
        """Async disconnect."""
        if self.client:
            try:
                await self.client.disconnect()
            except Exception:
                pass
            self.client = None
