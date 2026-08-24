"""
Deriv (Binary.com) broker adapter for RDE Platform.

Suporta duas APIs:
  - Nova API (OTP): PAT + app_id -> REST OTP -> WebSocket autenticado
  - API legada (v3): wss://ws.derivws.com/websockets/v3?app_id=X + authorize(token)

Fallback: tenta nova API primeiro; se falhar, usa legada.
"""
import json
import time
import logging
import threading
import asyncio
import websockets
import requests

from src.broker.base import BaseBroker
from src.broker._utils import run_async

logger = logging.getLogger("rde")

DERIV_REST_BASE = "https://api.derivws.com"
DERIV_APP_ID = "33SfcF4w0z4WC5y23w4pF"
WS_LEGACY = "wss://ws.derivws.com/websockets/v3"


class DerivBroker(BaseBroker):

    def __init__(self, api_token: str, is_demo: bool = True, app_id: str = DERIV_APP_ID):
        self.api_token = api_token
        self.is_demo = is_demo
        self.app_id = app_id
        self._ws = None
        self._ws_lock = threading.Lock()
        self._req_id = 0
        self._auth_mode = None

    # ------------------------------------------------------------------ #
    # REST helpers (Nova API OTP)
    # ------------------------------------------------------------------ #
    def _rest_headers(self):
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Deriv-App-ID": str(self.app_id),
            "Content-Type": "application/json",
        }

    def _get_accounts(self):
        url = f"{DERIV_REST_BASE}/trading/v1/options/accounts"
        resp = requests.get(url, headers=self._rest_headers(), timeout=20)
        resp.raise_for_status()
        return resp.json().get("data", [])

    def _get_otp_url(self, account_id: str) -> str:
        url = f"{DERIV_REST_BASE}/trading/v1/options/accounts/{account_id}/otp"
        resp = requests.post(url, headers=self._rest_headers(), data="{}", timeout=20)
        resp.raise_for_status()
        return resp.json()["data"]["url"]

    def _resolve_account_id(self):
        accounts = self._get_accounts()
        wanted = "demo" if self.is_demo else "real"
        logger.info(f"[Deriv] _resolve: wanted={wanted}, accounts={[(a.get('account_id'), a.get('account_type')) for a in accounts]}")
        if accounts:
            for acc in accounts:
                if (acc.get("account_type") or "").lower() == wanted:
                    logger.info(f"[Deriv] _resolve: selected {acc.get('account_id')} ({acc.get('account_type')})")
                    return acc["account_id"]
        try:
            url = f"{DERIV_REST_BASE}/trading/v1/options/accounts"
            body = json.dumps({"currency": "USD", "group": "row", "account_type": wanted})
            resp = requests.post(url, headers=self._rest_headers(), data=body, timeout=20)
            resp.raise_for_status()
            data = resp.json().get("data")
            if isinstance(data, list):
                return data[0]["account_id"]
            return data["account_id"]
        except Exception as e:
            logger.warning(f"Falha ao criar conta Deriv ({wanted}): {e}")
            if accounts:
                return accounts[0]["account_id"]
            raise ConnectionError("Nenhuma conta Deriv disponivel para este token.")

    # ------------------------------------------------------------------ #
    # Connect (OTP + fallback legada v3)
    # ------------------------------------------------------------------ #
    def connect(self):
        run_async(self._connect_async())

    async def _connect_async(self):
        # 1. Tenta OTP
        try:
            account_id = await asyncio.to_thread(self._resolve_account_id)
            ws_url = await asyncio.to_thread(self._get_otp_url, account_id)
            self._ws = await websockets.connect(ws_url)
            self._auth_mode = "otp"
            logger.info(f"Deriv conectada via OTP account={account_id} demo={self.is_demo}")
            return True
        except Exception as e:
            logger.warning(f"OTP falhou ({e}), tentando API legada v3...")

        # 2. Legada v3
        ws_url = f"{WS_LEGACY}?app_id={self.app_id}"
        self._ws = await websockets.connect(ws_url)
        auth_payload = {"authorize": self.api_token, "req_id": self._next_req_id()}
        await self._ws.send(json.dumps(auth_payload))
        resp = json.loads(await asyncio.wait_for(self._ws.recv(), timeout=15))
        if resp.get("error"):
            raise ConnectionError(resp["error"].get("message", "Auth failed"))
        self._auth_mode = "legacy"
        login_id = resp.get("authorize", {}).get("loginid", "?")
        logger.info(f"Deriv conectada via legada v3: {login_id}")
        return True

    def _ensure_connected(self) -> bool:
        try:
            if self._ws is None or getattr(self._ws, "closed", True):
                self.connect()
                return True
            # Verifica se WS esta realmente vivo — sem run_async (evita event loop mismatch)
            try:
                if not getattr(self._ws, "closed", True):
                    return True
                logger.warning("Deriv WS fechado. Reconectando...")
            except Exception:
                pass
            logger.warning("Deriv WS parece morto. Reconectando...")
            try:
                run_async(self._ws.close())
            except Exception:
                pass
            self._ws = None
            self.connect()
            return True
        except Exception as e:
            logger.error(f"Falha ao conectar Deriv: {e}")
            return False

    async def _ensure_connected_async(self) -> bool:
        try:
            if self._ws is None or getattr(self._ws, "closed", True):
                await self._connect_async()
            return True
        except Exception as e:
            logger.error(f"Falha ao conectar Deriv: {e}")
            return False

    # ------------------------------------------------------------------ #
    # WebSocket request/response
    # ------------------------------------------------------------------ #
    def _next_req_id(self):
        with self._ws_lock:
            self._req_id += 1
            return self._req_id

    async def _ws_request(self, payload: dict, timeout: float = 30.0) -> dict:
        if self._ws is None or getattr(self._ws, "closed", True):
            await self._connect_async()
        req_id = self._next_req_id()
        payload = dict(payload)
        payload["req_id"] = req_id
        await self._ws.send(json.dumps(payload))
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            raw = await asyncio.wait_for(self._ws.recv(), timeout=min(remaining, timeout))
            msg = json.loads(raw)
            if msg.get("req_id") == req_id:
                return msg
        raise TimeoutError(f"Sem resposta para req_id={req_id}")

    # ------------------------------------------------------------------ #
    # Send order
    # ------------------------------------------------------------------ #
    def send_order(self, symbol: str, stake: float, direction: str, duration: int = 1) -> dict:
        if not self._ensure_connected():
            return {"status": "error", "result": "Falha ao conectar Deriv"}
        return run_async(self._send_order_async(symbol, stake, direction, duration))

    async def async_send_order(self, symbol: str, stake: float, direction: str, duration: int = 1) -> dict:
        if not await self._ensure_connected_async():
            return {"status": "error", "result": "Falha ao conectar Deriv"}
        return await self._send_order_async(symbol, stake, direction, duration)

    # Deriv minimum = 2 min; fixed expiration = 3 min for all orders.
    DERIV_EXPIRATION_MINUTES = 3

    async def _send_order_async(self, symbol: str, stake: float, direction: str, duration: int = 1) -> dict:
        duration = self.DERIV_EXPIRATION_MINUTES
        contract_type = "CALL" if direction.upper() == "CALL" else "PUT"
        proposal_req = {
            "proposal": 1,
            "amount": float(stake),
            "basis": "stake",
            "contract_type": contract_type,
            "currency": "USD",
            "duration": int(duration),
            "duration_unit": "m",
            "underlying_symbol": symbol,
        }
        prop = await self._ws_request(proposal_req)
        if "error" in prop:
            logger.error(f"Deriv proposal error: {prop['error']['message']}")
            return {"status": "error", "result": prop["error"]["message"]}
        proposal_id = prop["proposal"]["id"]
        buy_req = {"buy": proposal_id, "price": float(stake)}
        res = await self._ws_request(buy_req)
        if "error" in res:
            logger.error(f"Deriv buy error: {res['error']['message']}")
            return {"status": "error", "result": res["error"]["message"]}
        buy = res.get("buy", {})
        return {
            "status": "ok",
            "result": "Sucesso",
            "contract_id": str(buy.get("contract_id")),
            "entry_price": float(buy.get("buy_price", stake)),
            "transaction_id": buy.get("transaction_id"),
        }

    # ------------------------------------------------------------------ #
    # Balance
    # ------------------------------------------------------------------ #
    def get_balance(self) -> float:
        return run_async(self._get_balance_async())

    async def _get_balance_async(self) -> float:
        res = await self._ws_request({"balance": 1})
        if "error" in res:
            raise ConnectionError(res["error"]["message"])
        return float(res.get("balance", {}).get("balance", 0.0))

    # ------------------------------------------------------------------ #
    # Contract status
    # ------------------------------------------------------------------ #
    def get_contract_status(self, contract_id: str) -> str:
        return run_async(self._get_contract_status_async(contract_id))

    async def _get_contract_status_async(self, contract_id: str) -> str:
        await asyncio.sleep(62)
        res = await self._ws_request({"proposal_open_contract": 1, "contract_id": int(contract_id)})
        contract = res.get("proposal_open_contract", {})
        status = contract.get("status")
        if status == "won":
            return "won"
        elif status == "lost":
            return "lost"
        return "error"

    # ------------------------------------------------------------------ #
    # Disconnect
    # ------------------------------------------------------------------ #
    def disconnect(self):
        if self._ws:
            try:
                run_async(self._ws.close())
            except Exception:
                pass
            self._ws = None
