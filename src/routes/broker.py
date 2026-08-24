from __future__ import annotations

import uuid
import time
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database.session import get_async_session
from src.auth.users import current_active_user
from src.models.user import User
from src.models.broker import BrokerSetting, BrokerType
from src.core.security import encryption_service
from pydantic import BaseModel

logger = logging.getLogger("rde")

# Alerta de vencimento do PAT da Deriv: avisa quando faltam <= 90 dias
DERIV_TOKEN_WARN_DAYS = 90


def _deriv_expiry_warning(setting: BrokerSetting) -> Optional[str]:
    """Retorna mensagem de aviso se o PAT da Deriv vence em <= 90 dias (ou ja venceu)."""
    exp = getattr(setting, "deriv_token_expiry", None)
    if not exp:
        return None
    if exp.tzinfo is not None:
        exp = exp.replace(tzinfo=None)
    days_left = (exp - datetime.utcnow()).days
    if days_left <= DERIV_TOKEN_WARN_DAYS:
        if days_left < 0:
            return f"ATENCAO: o PAT da Deriv venceu ha {-days_left} dias. Gere um novo token em developers.deriv.com."
        return f"ATENCAO: o PAT da Deriv vence em {days_left} dias. Gere um novo token em developers.deriv.com."
    return None


router = APIRouter(prefix="/broker", tags=["broker"])

# Cache de conexoes broker para refresh-balance (evita reconexao a cada 30s)
_broker_refresh_cache: dict = {}
_refresh_cache_lock = threading.Lock()
_CACHE_TTL = 120  # 2 minutos


class BrokerCreate(BaseModel):
    broker_name: str
    api_token: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    is_demo: bool = True
    deriv_app_id: Optional[str] = None
    deriv_token_expiry: Optional[str] = None


class BrokerStatusResponse(BaseModel):
    broker: str
    is_active: bool
    is_demo: bool
    has_token: bool
    has_email: bool


class BrokerSettingsInfo(BaseModel):
    broker_name: str
    is_demo: bool
    has_token: bool
    deriv_app_id: Optional[str] = None
    deriv_token_expiry: Optional[str] = None


@router.get("/settings/{broker_name}", response_model=BrokerSettingsInfo)
async def get_broker_settings_info(
    broker_name: str,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    stmt = select(BrokerSetting).where(
        BrokerSetting.user_id == user.id,
        BrokerSetting.broker_name == broker_name.lower(),
    )
    result = await db.execute(stmt)
    setting = result.scalar_one_or_none()
    if not setting:
        return BrokerSettingsInfo(
            broker_name=broker_name, is_demo=True, has_token=False,
        )
    return BrokerSettingsInfo(
        broker_name=setting.broker_name,
        is_demo=setting.is_demo,
        has_token=bool(setting.api_token),
        deriv_app_id=getattr(setting, "deriv_app_id", None),
        deriv_token_expiry=str(setting.deriv_token_expiry) if getattr(setting, "deriv_token_expiry", None) else None,
    )


@router.post("/settings")
async def save_broker_settings(
    settings: BrokerCreate,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Save or update broker credentials (encrypted).
    is_demo is taken from the request payload.
    Validates if broker is allowed for user's plan.
    """
    broker_name_lower = settings.broker_name.lower()

    # Recarrega user com plan para evitar lazy-load em contexto async
    user_stmt = select(User).options(selectinload(User.plan)).where(User.id == user.id)
    user_result = await db.execute(user_stmt)
    full_user = user_result.scalar_one_or_none()
    if not full_user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    # Validar se o broker é permitido pelo plano do usuário
    # Superuser/Admin ignora restrições de plano
    if not (full_user.is_superuser or full_user.is_admin):
        if full_user.plan and full_user.plan.allowed_brokers:
            allowed = full_user.plan.get_allowed_brokers()
            if allowed and broker_name_lower not in allowed:
                raise HTTPException(
                    status_code=403,
                    detail=f"Broker '{broker_name_lower}' não permitido no seu plano ({full_user.plan.name}). Permitidos: {', '.join(allowed)}"
                )

    # Check if entry already exists for this user/broker
    stmt = select(BrokerSetting).where(
        BrokerSetting.user_id == user.id,
        BrokerSetting.broker_name == broker_name_lower
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    # Unifica e-mail + senha no campo api_token
    if broker_name_lower in ("iqoption", "quotex"):
        if settings.email and settings.password:
            credential_token = f"{settings.email}|||{settings.password}"
        else:
            credential_token = settings.email or settings.api_token
    else:
        credential_token = settings.api_token

    # Criptografa o token unificado
    enc_token = encryption_service.encrypt(credential_token) if credential_token else None

    if existing:
        if enc_token:
            existing.api_token = enc_token
        existing.is_demo = settings.is_demo
        existing.is_active = True
        if broker_name_lower == "deriv":
            if settings.deriv_app_id:
                existing.deriv_app_id = settings.deriv_app_id
            if settings.deriv_token_expiry is not None:
                try:
                    existing.deriv_token_expiry = datetime.fromisoformat(settings.deriv_token_expiry) if isinstance(settings.deriv_token_expiry, str) else settings.deriv_token_expiry
                except (ValueError, TypeError):
                    pass
    else:
        try:
            broker_type = BrokerType(broker_name_lower)
        except ValueError:
            broker_type = BrokerType.IQOPTION
        new_setting = BrokerSetting(
            user_id=user.id,
            broker_type=broker_type,
            broker_name=broker_name_lower,
            api_token=enc_token,
            is_demo=settings.is_demo,
            is_active=True,
        )
        if broker_name_lower == "deriv":
            if settings.deriv_app_id:
                new_setting.deriv_app_id = settings.deriv_app_id
            if settings.deriv_token_expiry is not None:
                try:
                    new_setting.deriv_token_expiry = datetime.fromisoformat(settings.deriv_token_expiry) if isinstance(settings.deriv_token_expiry, str) else settings.deriv_token_expiry
                except (ValueError, TypeError):
                    pass
        db.add(new_setting)

    user.broker = broker_name_lower
    db.add(user)
    await db.commit()
    return {"status": "success", "message": f"Settings for {settings.broker_name} saved securely."}

@router.get("/status", response_model=List[BrokerStatusResponse])
async def get_broker_status(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Fetch connection status and active mode for all configured brokers.
    """
    stmt = select(BrokerSetting).where(BrokerSetting.user_id == user.id)
    result = await db.execute(stmt)
    settings_list = result.scalars().all()

    # Como não usamos a coluna 'email' no banco para IQ Option, 
    # validamos a existência do e-mail checando o campo api_token
    return [
        BrokerStatusResponse(
            broker=s.broker_name,
            is_active=s.is_active,
            is_demo=s.is_demo,
            has_token=bool(s.api_token) if s.broker_name != "iqoption" else False,
            has_email=bool(s.api_token) if s.broker_name == "iqoption" else bool(s.iq_email)
        ) for s in settings_list
    ]


class BrokerActivateRequest(BaseModel):
    broker_name: str


@router.post("/activate")
async def activate_broker(
    req: BrokerActivateRequest,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Switch the active broker. Deactivates all others and activates the specified one.
    Validates if broker is allowed for user's plan.
    """
    broker_name = req.broker_name.lower()
    valid = {"iqoption", "quotex", "pocketoption", "deriv"}

    if broker_name not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"Corretora inválida. Suportadas: {', '.join(valid)}"
        )

    # Recarrega user com plan para evitar lazy-load em contexto async
    user_stmt = select(User).options(selectinload(User.plan)).where(User.id == user.id)
    user_result = await db.execute(user_stmt)
    full_user = user_result.scalar_one_or_none()
    if not full_user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    # Validar se o broker é permitido pelo plano do usuário
    # Superuser/Admin ignora restrições de plano
    if not (full_user.is_superuser or full_user.is_admin):
        if full_user.plan and full_user.plan.allowed_brokers:
            allowed = full_user.plan.get_allowed_brokers()
            if allowed and broker_name not in allowed:
                raise HTTPException(
                    status_code=403,
                    detail=f"Broker '{broker_name}' não permitido no seu plano ({full_user.plan.name}). Permitidos: {', '.join(allowed)}"
                )

    # Ativa o broker alvo sem desativar as demais (multi-broker ativo)
    stmt = select(BrokerSetting).where(BrokerSetting.user_id == user.id)
    result = await db.execute(stmt)
    all_settings = result.scalars().all()

    target = None
    for s in all_settings:
        if s.broker_name == broker_name:
            s.is_active = True
            target = s

    if not target:
        raise HTTPException(
            status_code=404,
            detail=f"Nenhuma configuração encontrada para '{broker_name}'. Salve as credenciais primeiro."
        )

    # Define como broker principal (referência para dashboard/executor)
    user.broker = broker_name
    db.add(user)
    await db.commit()

    active_names = [s.broker_name for s in all_settings if s.is_active]

    return {
        "status": "success",
        "message": f"{broker_name.upper()} ativada. Corretoras ativas: {', '.join(active_names)}.",
        "is_demo": target.is_demo,
        "active_brokers": active_names,
    }


class BrokerToggleModeRequest(BaseModel):
    broker_name: str
    is_demo: bool


@router.patch("/toggle-mode")
async def toggle_broker_mode(
    req: BrokerToggleModeRequest,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Toggle a broker between Demo and Real mode.
    Respects plan-level is_demo setting.
    """
    broker_name_lower = req.broker_name.lower()

    stmt = select(BrokerSetting).where(
        BrokerSetting.user_id == user.id,
        BrokerSetting.broker_name == broker_name_lower,
    )
    result = await db.execute(stmt)
    setting = result.scalar_one_or_none()

    if not setting:
        raise HTTPException(
            status_code=404,
            detail=f"Configurações não encontradas para a corretora '{req.broker_name}'."
        )

    setting.is_demo = req.is_demo
    await db.commit()

    mode = "Demo" if setting.is_demo else "Real"
    return {
        "status": "success",
        "message": f"{req.broker_name.upper()} alterada para modo {mode} (definido pelo plano).",
        "is_demo": setting.is_demo,
    }


@router.post("/test-connection")
async def test_broker_connection(
    req: BrokerActivateRequest,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Test real connection to the broker and return balance.
    """
    broker_name = req.broker_name.lower()

    stmt = select(BrokerSetting).where(
        BrokerSetting.user_id == user.id,
        BrokerSetting.broker_name == broker_name,
    )
    result = await db.execute(stmt)
    setting = result.scalar_one_or_none()

    if not setting:
        return {"status": "error", "message": f"Corretora '{broker_name}' não configurada."}

    def _decrypt(val):
        if not val:
            return None
        try:
            dec = encryption_service.decrypt(val)
            return dec if dec != "ERROR_DECRYPT" else val
        except Exception:
            return val

    try:
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        def _connect_and_balance():
            import time
            # --- IQ OPTION ---
            if broker_name == "iqoption":
                from src.broker.iqoption import IQOptionBroker
                
                # 💡 Lendo o email+senha do campo api_token de forma descriptografada
                creds = _decrypt(setting.api_token) or ""
                if "|||" in creds:
                    email, password = creds.split("|||", 1)
                else:
                    email, password = creds, ""
                
                if not email or not password:
                    return {"status": "error", "message": "Credenciais IQ Option não configuradas."}
                    
                b = IQOptionBroker(email=email, password=password, is_demo=setting.is_demo)
                b.connect()
                time.sleep(2)
                balance = b.get_balance()
                if balance is None:
                    balance = 0.0
                mode = "Demo" if setting.is_demo else "Real"
                return {"status": "ok", "message": "Conectado!", "balance": float(balance), "mode": mode}

            # --- QUOTEX ---
            elif broker_name == "quotex":
                from src.broker.quotex import QuotexBroker
                creds = _decrypt(setting.api_token) or ""
                if "|||" in creds:
                    email, password = creds.split("|||", 1)
                else:
                    email, password = creds, ""
                if not email or not password:
                    return {"status": "error", "message": "Credenciais Quotex não configuradas."}
                b = QuotexBroker(email=email, password=password, is_demo=setting.is_demo)
                b.connect()
                balance = b.get_balance()
                mode = "Demo" if setting.is_demo else "Real"
                return {"status": "ok", "message": "Conectado!", "balance": float(balance or 0), "mode": mode}

            # --- POCKET OPTION ---
            elif broker_name == "pocketoption":
                from src.broker.pocketoption import PocketOptionBroker
                ssid = _decrypt(setting.api_token)
                if not ssid:
                    return {"status": "error", "message": "SSID Pocket Option não configurado."}
                b = PocketOptionBroker(ssid=ssid, is_demo=setting.is_demo)
                b.connect()
                balance = b.get_balance()
                mode = "Demo" if setting.is_demo else "Real"
                return {"status": "ok", "message": "Conectado!", "balance": float(balance or 0), "mode": mode}

            # --- DERIV ---
            elif broker_name in ("deriv", "deriv_demo", "deriv_real"):
                from src.broker.deriv import DerivBroker
                token = _decrypt(setting.api_token)
                if not token:
                    return {"status": "error", "message": "Token Deriv nao configurado."}
                b = DerivBroker(api_token=token, is_demo=setting.is_demo, app_id=getattr(setting, "deriv_app_id", None) or "16929")
                b.connect()
                balance = b.get_balance()
                return {"status": "ok", "message": "Conectado!", "balance": float(balance or 0), "mode": "Demo" if setting.is_demo else "Real"}

            return {"status": "error", "message": f"Corretora '{broker_name}' nao suportada."}

        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            result = await loop.run_in_executor(pool, _connect_and_balance)
        
        # Save balance to DB so dashboard can read it
        if result.get("status") == "ok":
            setting.balance = result.get("balance", 0)
            db.add(setting)
            await db.commit()
        return result

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/refresh-balance")
async def refresh_balance(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Conecta em TODAS as corretoras ativas, busca o saldo em tempo real
    e atualiza o banco. Retorna o saldo de cada uma + total.
    Usa cache de conexao para evitar reconexao a cada 30 segundos.
    """
    stmt = select(BrokerSetting).where(
        BrokerSetting.user_id == user.id,
        BrokerSetting.is_active == True,
    )
    result = await db.execute(stmt)
    settings = result.scalars().all()

    if not settings:
        return {"status": "no_broker", "balance": 0.0, "broker": None, "brokers": []}

    def _decrypt(val):
        if not val:
            return None
        try:
            dec = encryption_service.decrypt(val)
            return dec if dec != "ERROR_DECRYPT" else val
        except Exception:
            return val

    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    def _fetch_one_balance(setting):
        """Busca o saldo de um único broker (com cache de conexao)."""
        broker_name = setting.broker_name.lower()
        cache_key = f"{user.id}_{broker_name}"

        # Verificar cache de conexao
        with _refresh_cache_lock:
            cached = _broker_refresh_cache.get(cache_key)
            if cached:
                age = time.time() - cached["created_at"]
                if age < _CACHE_TTL:
                    broker = cached["broker"]
                    try:
                        balance = broker.get_balance()
                        if balance and balance > 0:
                            logger.info(f"Broker balance from cache (age={age:.0f}s): ${balance}")
                            return {"broker": broker_name, "status": "ok", "balance": float(balance), "mode": "Demo" if setting.is_demo else "Real"}
                    except Exception:
                        pass
                    # Cache miss ou erro - remove
                    try:
                        broker.disconnect()
                    except Exception:
                        pass
                    _broker_refresh_cache.pop(cache_key, None)

        if broker_name == "iqoption":
            from src.broker.iqoption import IQOptionBroker
            creds = _decrypt(setting.api_token) or ""
            if "|||" in creds:
                email, password = creds.split("|||", 1)
            else:
                email, password = creds, ""
            if not email or not password:
                return {"broker": broker_name, "status": "error", "message": "Credenciais IQ Option incompletas."}
            b = IQOptionBroker(email=email, password=password, is_demo=setting.is_demo)
            b.connect()
            time.sleep(2)
            balance = b.get_balance()
            with _refresh_cache_lock:
                _broker_refresh_cache[cache_key] = {"broker": b, "created_at": time.time()}
            return {"broker": broker_name, "status": "ok", "balance": float(balance or 0), "mode": "Demo" if setting.is_demo else "Real"}

        elif broker_name == "quotex":
            from src.broker.quotex import QuotexBroker
            creds = _decrypt(setting.api_token) or ""
            email, password = creds.split("|||", 1) if "|||" in creds else (creds, "")
            if not email or not password:
                return {"broker": broker_name, "status": "error", "message": "Credenciais Quotex incompletas."}
            b = QuotexBroker(email=email, password=password, is_demo=setting.is_demo)
            b.connect()
            balance = b.get_balance()
            with _refresh_cache_lock:
                _broker_refresh_cache[cache_key] = {"broker": b, "created_at": time.time()}
            return {"broker": broker_name, "status": "ok", "balance": float(balance or 0), "mode": "Demo" if setting.is_demo else "Real"}

        elif broker_name == "pocketoption":
            from src.broker.pocketoption import PocketOptionBroker
            ssid = _decrypt(setting.api_token)
            if not ssid:
                return {"broker": broker_name, "status": "error", "message": "SSID Pocket Option nao configurado."}
            b = PocketOptionBroker(ssid=ssid, is_demo=setting.is_demo)
            b.connect()
            balance = b.get_balance()
            with _refresh_cache_lock:
                _broker_refresh_cache[cache_key] = {"broker": b, "created_at": time.time()}
            return {"broker": broker_name, "status": "ok", "balance": float(balance or 0), "mode": "Demo" if setting.is_demo else "Real"}

        elif broker_name in ("deriv", "deriv_demo", "deriv_real"):
            from src.broker.deriv import DerivBroker
            token = _decrypt(setting.api_token)
            if not token:
                return {"broker": broker_name, "status": "error", "message": "Token Deriv nao configurado."}
            b = DerivBroker(api_token=token, is_demo=setting.is_demo, app_id=getattr(setting, "deriv_app_id", None) or "16929")
            b.connect()
            balance = b.get_balance()
            with _refresh_cache_lock:
                _broker_refresh_cache[cache_key] = {"broker": b, "created_at": time.time()}
            return {"broker": broker_name, "status": "ok", "balance": float(balance or 0), "mode": "Demo" if setting.is_demo else "Real"}

        return {"broker": broker_name, "status": "error", "message": f"Corretora '{broker_name}' nao suportada."}

    try:
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            results = list(pool.map(_fetch_one_balance, settings))

        total_balance = 0.0
        connected = []
        errors = []
        for setting, res in zip(settings, results):
            if res.get("status") == "ok":
                setting.balance = res.get("balance", 0)
                setting.balance_updated_at = datetime.utcnow()
                total_balance += res.get("balance", 0)
                connected.append({
                    "broker": setting.broker_name,
                    "balance": res.get("balance", 0),
                    "mode": res.get("mode", "-"),
                    "connected": True,
                })
            else:
                errors.append(f"{setting.broker_name}: {res.get('message', 'erro')}")
                connected.append({
                    "broker": setting.broker_name,
                    "balance": setting.balance or 0,
                    "mode": "Demo" if setting.is_demo else "Real",
                    "connected": False,
                })
        db.add_all(settings)
        await db.commit()

        primary = next((c for c in connected if c["broker"] == (user.broker or "")), None) or (connected[0] if connected else None)

        return {
            "status": "ok" if connected and any(c["connected"] for c in connected) else "error",
            "balance": round(total_balance, 2),
            "mode": primary["mode"] if primary else "-",
            "broker": primary["broker"] if primary else (user.broker or "iqoption"),
            "brokers": connected,
            "message": " | ".join(errors) if errors else "Saldos atualizados.",
        }

    except Exception as e:
        return {"status": "error", "balance": 0.0, "broker": (user.broker or "iqoption"), "brokers": [], "message": str(e)}


class TestTradeRequest(BaseModel):
    broker_name: str
    direction: str = "CALL"
    stake: Optional[float] = None


@router.post("/test-trade")
async def test_trade(
    req: TestTradeRequest,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Place a test trade on the broker. Uses same code path as the copier."""
    broker_name = req.broker_name.lower()
    direction = req.direction.upper()
    if direction not in ("CALL", "PUT"):
        return {"status": "error", "message": "Direction must be CALL or PUT"}

    stmt = select(BrokerSetting).where(
        BrokerSetting.user_id == user.id,
        BrokerSetting.broker_name == broker_name,
    )
    result = await db.execute(stmt)
    setting = result.scalar_one_or_none()
    if not setting:
        return {"status": "error", "message": f"Corretora '{broker_name}' nao configurada."}

    def _decrypt(val):
        if not val: return None
        try:
            dec = encryption_service.decrypt(val)
            return dec if dec != "ERROR_DECRYPT" else val
        except Exception:
            return val

    import asyncio, time
    from concurrent.futures import ThreadPoolExecutor

    def _place_trade():
        stake = req.stake or (user.stake or 1.0)
        symbol_map = {"iqoption": "EURUSD", "deriv": "R_100"}
        symbol = symbol_map.get(broker_name, "EURUSD")

        if broker_name == "iqoption":
            from src.broker.iqoption import IQOptionBroker
            creds = _decrypt(setting.api_token) or ""
            email, password = creds.split("|||", 1) if "|||" in creds else (creds, "")
            if not email or not password:
                return {"status": "error", "message": "Credenciais IQ Option incompletas."}
            b = IQOptionBroker(email=email, password=password, is_demo=bool(setting.is_demo))
            b.connect()
            time.sleep(2)
            balance_before = b.get_balance()
            result = b.send_order(symbol=symbol, stake=stake, direction=direction)
            balance_after = b.get_balance()
            b.disconnect()

        elif broker_name in ("deriv", "deriv_demo", "deriv_real"):
            from src.broker.deriv import DerivBroker
            token = _decrypt(setting.api_token)
            if not token:
                return {"status": "error", "message": "Token Deriv nao configurado."}
            b = DerivBroker(api_token=token, is_demo=bool(setting.is_demo), app_id=getattr(setting, "deriv_app_id", None) or "16929")
            b.connect()
            balance_before = b.get_balance()
            result = b.send_order(symbol=symbol, stake=stake, direction=direction)
            balance_after = b.get_balance()
            b.disconnect()

        else:
            return {"status": "error", "message": f"Corretora '{broker_name}' nao suportada."}

        return {
            "status": "ok" if result.get("status") == "ok" else "error",
            "direction": direction,
            "stake": stake,
            "symbol": symbol,
            "mode": "Demo" if setting.is_demo else "Real",
            "result": result,
            "balance_before": float(balance_before or 0),
            "balance_after": float(balance_after or 0),
            "diff": float((balance_after or 0) - (balance_before or 0)),
        }

    try:
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            return await loop.run_in_executor(pool, _place_trade)
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ====================== AUDIT ENDPOINTS ======================
@router.get("/audit/trades")
async def get_audit_trades(
    limit: int = 50,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Historico de trades de hoje para auditoria."""
    from src.services.audit_service import get_trades_today
    return get_trades_today(limit=limit)


@router.get("/audit/summary")
async def get_audit_summary(
    user: User = Depends(current_active_user),
):
    """Resumo de trades de hoje."""
    from src.services.audit_service import get_trade_summary
    return get_trade_summary()