"""
TradingView Webhook Bridge — RDE Platform
Recebe sinais do TradingView via HTTP POST e executa na corretora.
Fluxo: TradingView Alert -> POST /tradingview/webhook -> RDE -> Broker (IQ Option/Deriv/etc.)

Melhorias vs copier Telegram:
- Cache de conexao broker (reusa mesma instancia)
- Symbol mapping por broker
- Tracking de resultado (espera win/loss, atualiza saldo)
"""
from __future__ import annotations
import os
import re
import time
import uuid
import asyncio
import threading
import logging
from datetime import datetime
from typing import Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from sqlalchemy.orm import selectinload
from src.database.session import get_async_session
from src.auth.users import current_active_user
from src.models.user import User
from src.models.broker import BrokerSetting

logger = logging.getLogger("RDE-TradingViewBridge")

router = APIRouter(prefix="/tradingview", tags=["TradingView Webhook"])


# ── Cache de conexoes broker (reusa instancia por user) ──────────────
_broker_cache: Dict[str, dict] = {}
_cache_lock = threading.Lock()


def _cache_key(user_id: int, broker_setting_id) -> str:
    return f"{user_id}_{broker_setting_id}"


def _get_cached_broker(user_id: int, broker_setting_id, broker_name: str):
    """Retorna broker em cache ou cria novo. Verifica saude do broker em cache."""
    key = _cache_key(user_id, broker_setting_id)
    with _cache_lock:
        entry = _broker_cache.get(key)
        if entry:
            broker = entry["broker"]
            age = time.time() - entry["created_at"]
            if age < 600:
                try:
                    bal = broker.get_balance()
                    if bal is not None and bal >= 0:
                        logger.info(f"Broker reutilizado do cache (idade={age:.0f}s, saldo=${bal:.2f})")
                        return broker
                    else:
                        logger.warning(f"Broker em cache com saldo invalido ({bal}). Reconectando...")
                except Exception as e:
                    logger.warning(f"Broker em cache falhou no health check ({e}). Reconectando...")
                try:
                    broker.disconnect()
                except Exception:
                    pass
                del _broker_cache[key]
            else:
                logger.info(f"Broker em cache expirado ({age:.0f}s). Reconectando...")
                try:
                    broker.disconnect()
                except Exception:
                    pass
                del _broker_cache[key]

    broker = _create_broker(user_id, broker_name)
    with _cache_lock:
        _broker_cache[key] = {
            "broker": broker,
            "created_at": time.time(),
        }
    return broker


def _create_broker(user_id: int, broker_name: str):
    """Cria e conecta um novo broker (chamado pelo cache)."""
    from src.broker.iqoption import IQOptionBroker
    from src.broker.deriv import DerivBroker
    from src.broker.quotex import QuotexBroker
    from src.broker.pocketoption import PocketOptionBroker

    from src.database.session import SessionLocal
    db = SessionLocal()
    try:
        user = (
            db.query(User)
            .options(selectinload(User.broker_settings))
            .filter(User.id == user_id)
            .first()
        )
        if not user:
            raise ValueError(f"User {user_id} not found")

        setting = next(
            (bs for bs in user.broker_settings if bs.is_active and (bs.broker_name or "").lower() == broker_name.lower()),
            None,
        )
        if not setting:
            setting = next(
                (bs for bs in user.broker_settings if bs.is_active),
                None,
            )
        if not setting:
            raise ValueError("Nenhum broker configurado")

        def _decrypt(cipher_text):
            if not cipher_text:
                return None
            try:
                from src.core.security import encryption_service
                decrypted = encryption_service.decrypt(cipher_text)
                return decrypted if decrypted != "ERROR_DECRYPT" else cipher_text
            except Exception:
                return cipher_text

        is_demo = bool(setting.is_demo)

        if broker_name == "iqoption":
            email, password = None, None
            if setting.api_token:
                token = _decrypt(setting.api_token)
                if token and "|||" in token:
                    email, password = token.split("|||", 1)
                elif setting.iq_email:
                    email = setting.iq_email
                    password = token
            if not email:
                email = user.iq_email
            if not password and user.iq_password:
                password = _decrypt(user.iq_password)
            if not email or not password:
                raise ValueError("IQ Option credentials not configured")
            broker = IQOptionBroker(email=email, password=password, is_demo=is_demo)
            broker.connect()
            if not broker._asset_map:
                logger.warning("IQ Option conectado mas asset map vazio. Tentando recarregar...")
                broker._wait_init()
                if not broker._asset_map:
                    logger.error("IQ Option asset map continuou vazio apos reconexao.")
            return broker

        elif broker_name in ("deriv", "deriv_demo", "deriv_real"):
            token = _decrypt(setting.api_token) if setting.api_token else None
            if not token:
                raise ValueError("Deriv API token not configured")
            broker = DerivBroker(api_token=token, is_demo=is_demo, app_id=getattr(setting, "deriv_app_id", None) or "16929")
            broker.connect()
            return broker

        elif broker_name == "quotex":
            creds = _decrypt(setting.api_token) if setting.api_token else None
            if not creds:
                raise ValueError("Quotex credentials not configured")
            email, password = creds.split("|||", 1) if "|||" in creds else (creds, "")
            if not email or not password:
                raise ValueError("Quotex credentials not configured")
            broker = QuotexBroker(email=email, password=password, is_demo=is_demo)
            broker.connect()
            return broker

        elif broker_name == "pocketoption":
            ssid = _decrypt(setting.api_token) if setting.api_token else None
            if not ssid:
                raise ValueError("Pocket Option SSID not configured")
            broker = PocketOptionBroker(ssid=ssid, is_demo=is_demo)
            broker.connect()
            return broker

        else:
            raise ValueError(f"Unsupported broker: {broker_name}")
    finally:
        db.close()


# ── Symbol mapping (TradingView -> corretora) ───────────────────────
def _map_symbol(symbol: str, broker_name: str) -> str:
    """Mapeia simbolo do TradingView para formato da corretora."""
    sym = symbol.upper().strip()
    sym_clean = re.sub(r'[^A-Z0-9_\-]', '', sym)

    if broker_name == "iqoption":
        sym_clean = sym_clean.replace("_OTC", "-OTC").replace("_OTCI", "-OTC")
        sym_clean = re.sub(r'-OTC[A-Z]$', '-OTC', sym_clean)
        return sym_clean

    elif broker_name in ("deriv", "deriv_demo", "deriv_real"):
        from src.broker.deriv_symbols import resolve_deriv_symbol
        return resolve_deriv_symbol(sym_clean)

    return sym_clean


# ── SessionManager cache (por user, persiste entre sinais) ──────────
_session_cache: Dict[int, dict] = {}


def _get_session_manager(user_id: int, balance: float, broker_name: str = ""):
    """Retorna SessionManager existente ou cria novo. Reseta diariamente."""
    from src.services.management_3pct import SessionManager
    today = datetime.now().strftime("%Y-%m-%d")
    cache_key = f"{user_id}_{broker_name}"
    with _cache_lock:
        entry = _session_cache.get(cache_key)
        if entry:
            sm = entry["manager"]
            if entry.get("date") != today or entry.get("broker") != broker_name:
                logger.info(f"Novo dia/broker detectado para user {user_id}. Resetando SessionManager.")
                sm = SessionManager(balance)
                _session_cache[cache_key] = {"manager": sm, "created_at": time.time(), "date": today, "broker": broker_name}
                return sm
            sm.update_balance(balance)
            return sm

    sm = SessionManager(balance)
    with _cache_lock:
        _session_cache[cache_key] = {"manager": sm, "created_at": time.time(), "date": today, "broker": broker_name}
    return sm


# ── Schema de entrada ────────────────────────────────────────────────
class TradingViewWebhookRequest(BaseModel):
    symbol: str
    direction: str
    expiry_minutes: int = 1
    timeframe: str = "1m"
    entry_price: Optional[float] = None
    passphrase: str = ""


class TradingViewWebhookResponse(BaseModel):
    status: str
    message: str
    stake: Optional[float] = None
    direction: Optional[str] = None
    symbol: Optional[str] = None
    result: Optional[str] = None
    profit: Optional[float] = None
    session_info: Optional[dict] = None


# ── Endpoints ────────────────────────────────────────────────────────
@router.post("/webhook", response_model=TradingViewWebhookResponse)
async def receive_tradingview_webhook(
    req: TradingViewWebhookRequest,
    secret: Optional[str] = Query(None, alias="secret"),
    db: AsyncSession = Depends(get_async_session),
):
    auth_key = req.passphrase or secret
    if not auth_key:
        raise HTTPException(status_code=401, detail="Passphrase ou secret obrigatorio.")

    user = await _authenticate_webhook(auth_key, db)
    if not user:
        raise HTTPException(status_code=401, detail="Passphrase invalida ou usuario inativo.")

    if user.signal_source != "tradingview":
        return TradingViewWebhookResponse(
            status="rejected",
            message="Modo de sinal nao e TradingView. Ative 'TradingView Webhook' na configuracao.",
        )

    broker_settings = _get_active_brokers(user)
    if not broker_settings:
        return TradingViewWebhookResponse(
            status="rejected",
            message="Nenhum broker configurado. Ative pelo menos uma corretora.",
        )

    direction = req.direction.upper().strip()
    if direction not in ("CALL", "PUT", "BUY", "SELL"):
        return TradingViewWebhookResponse(
            status="rejected",
            message=f"Direcao invalida: {req.direction}. Use CALL/PUT ou BUY/SELL.",
        )
    if direction in ("BUY", "CALL"):
        direction = "CALL"
    else:
        direction = "PUT"

    from src.models.risk_term import RiskTermAcceptance
    result = await db.execute(
        select(RiskTermAcceptance).where(RiskTermAcceptance.user_id == user.id)
    )
    risk = result.scalar_one_or_none()
    if not risk or not risk.accepted:
        return TradingViewWebhookResponse(
            status="rejected",
            message="BLOQUEADO: Aceite o Termo de Risco na plataforma.",
        )

    # Executa o sinal em TODAS as corretoras ativas (multi-broker)
    # Execução paralela com timeout por corretora para não travar o webhook
    BROKER_EXEC_TIMEOUT = 25  # segundos por corretora

    async def _run_one(broker_setting):
        try:
            trade_result = await asyncio.wait_for(
                _execute_tv_trade(
                    user=user,
                    broker_setting=broker_setting,
                    symbol=req.symbol,
                    direction=direction,
                    duration=req.expiry_minutes,
                    db=db,
                ),
                timeout=BROKER_EXEC_TIMEOUT,
            )
            return broker_setting, trade_result, None
        except asyncio.TimeoutError:
            logger.error(f"Timeout ao executar sinal TradingView em {broker_setting.broker_name}")
            return broker_setting, None, "Timeout na conexao com a corretora."
        except Exception as e:
            logger.error(f"Erro ao executar sinal TradingView em {broker_setting.broker_name}: {e}")
            return broker_setting, None, str(e)

    results = await asyncio.gather(*[_run_one(bs) for bs in broker_settings])

    executed = []
    rejected = []
    errors = []
    for broker_setting, trade_result, error in results:
        if trade_result is None:
            errors.append({
                "broker": broker_setting.broker_name,
                "status": "error",
                "message": error,
            })
        elif trade_result.status == "executed":
            executed.append({
                "broker": broker_setting.broker_name,
                "status": trade_result.status,
                "message": trade_result.message,
                "stake": trade_result.stake,
            })
        else:
            rejected.append({
                "broker": broker_setting.broker_name,
                "status": trade_result.status,
                "message": trade_result.message,
            })

    if executed:
        summary = f"Sinal executado em {len(executed)} corretora(s)."
        return TradingViewWebhookResponse(
            status="executed",
            message=summary,
            direction=direction,
            symbol=req.symbol,
            session_info={
                "executed": executed,
                "rejected": rejected,
                "errors": errors,
            },
        )

    if rejected:
        first = rejected[0]
        return TradingViewWebhookResponse(
            status=first["status"],
            message=first["message"],
            session_info={"executed": executed, "rejected": rejected, "errors": errors},
        )

    return TradingViewWebhookResponse(
        status="error",
        message=f"Erro ao executar sinal: {errors[0]['message'] if errors else 'desconhecido'}",
    )


@router.get("/status")
async def tv_status(user: User = Depends(current_active_user)):
    return {
        "signal_source": user.signal_source,
        "webhook_secret": user.webhook_secret or None,
        "webhook_endpoint": "/tradingview/webhook",
    }


@router.post("/generate-secret")
async def generate_webhook_secret(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    new_secret = f"tv_{uuid.uuid4().hex[:32]}"
    user.webhook_secret = new_secret
    db.add(user)
    await db.commit()
    logger.info(f"Webhook secret gerado para {user.email}")
    return {"webhook_secret": new_secret, "message": "Copie esta chave para o webhook do TradingView."}


# ── Helpers ──────────────────────────────────────────────────────────
async def _authenticate_webhook(passphrase: str, db: AsyncSession) -> Optional[User]:
    if not passphrase:
        return None
    result = await db.execute(
        select(User)
        .options(selectinload(User.broker_settings))
        .where(User.webhook_secret == passphrase, User.is_active == True)
    )
    return result.scalar_one_or_none()


def _get_active_brokers(user: User) -> list:
    """Retorna TODOS os brokers ativos do usuário (multi-broker)."""
    return [bs for bs in user.broker_settings if bs.is_active]


def _get_active_broker(user: User) -> Optional[BrokerSetting]:
    """Retorna o broker principal ativo (para compatibilidade)."""
    primary = next(
        (bs for bs in user.broker_settings if bs.is_active and bs.broker_name == (user.broker or "").lower()),
        None,
    )
    if primary:
        return primary
    return next(
        (bs for bs in user.broker_settings if bs.is_active),
        None,
    )


async def _execute_tv_trade(
    user: User,
    broker_setting: BrokerSetting,
    symbol: str,
    direction: str,
    duration: int,
    db: AsyncSession,
) -> TradingViewWebhookResponse:
    from src.services.management_3pct import SessionManager

    broker_name = (broker_setting.broker_name or "iqoption").lower()
    initial_balance = broker_setting.balance if broker_setting.balance and broker_setting.balance > 0 else 100.0
    session_manager = _get_session_manager(user.id, initial_balance, broker_name)

    if not session_manager.can_trade():
        sm = session_manager.get_status()
        return TradingViewWebhookResponse(
            status="rejected",
            message=f"Sessoes concluidas. Lucro do dia: ${sm['daily_profit']:.2f}",
            session_info=sm,
        )

    if broker_setting.auto_lock_meta and broker_setting.meta_hit_today:
        today = datetime.now().strftime("%Y-%m-%d")
        if broker_setting.meta_hit_date and broker_setting.meta_hit_date != today:
            logger.info(f"Novo dia ({today}). Resetando meta do broker {broker_setting.broker_name}")
            broker_setting.meta_hit_today = False
            broker_setting.meta_hit_date = None
            broker_setting.today_trades = 0
            broker_setting.today_profit = 0.0
            db.add(broker_setting)
            await db.commit()
        elif broker_setting.meta_hit_date == today:
            sm = session_manager.get_status()
            return TradingViewWebhookResponse(
                status="rejected",
                message=f"Meta diaria ja atingida. Bloqueado ate amanha. Lucro: ${sm['daily_profit']:.2f}",
                session_info=sm,
            )

    stake = session_manager.stake
    mapped_symbol = _map_symbol(symbol, broker_name)

    logger.info(
        f"TV TRADE: {direction} {symbol} -> {mapped_symbol} | "
        f"Stake: ${stake:.2f} | Sessao {session_manager.get_status()['current_session']}/3"
    )

    try:
        broker = _get_cached_broker(user.id, broker_setting.id, broker_name)
    except Exception as e:
        logger.error(f"Falha ao conectar broker: {e}")
        with _cache_lock:
            key = _cache_key(user.id, broker_setting.id)
            _broker_cache.pop(key, None)
        return TradingViewWebhookResponse(
            status="error",
            message=f"Falha ao conectar broker: {str(e)}",
        )

    balance_before = initial_balance

    try:
        import json
        from datetime import datetime as _dt
        sm_snap = session_manager.get_status()
        live = {
            "broker": broker_name,
            "account_mode": "Demo",
            "initial_balance": round(session_manager.initial_balance, 2),
            "current_balance": round(session_manager.current_balance, 2),
            "profit": round(sm_snap.get("daily_profit", 0), 2),
            "profit_pct": round((sm_snap.get("daily_profit", 0) / session_manager.initial_balance * 100), 2) if session_manager.initial_balance > 0 else 0,
            "current_stake": round(stake, 2),
            "signals_today": sm_snap.get("total_trades", 0),
            "success_count": sm_snap.get("wins", 0),
            "success_rate": sm_snap.get("win_rate", 0),
            "gale_level": sm_snap.get("gale_level", 0),
            "last_message": f"TV: {direction} {mapped_symbol} M{duration} — executando...",
            "timestamp": _dt.now().strftime("%H:%M:%S"),
            "meta_hit_today": False,
            "auto_lock_meta": True,
            "source": "tradingview",
        }
        with open(f"live_status_{user.id}.json", "w") as f:
            json.dump(live, f)
    except Exception:
        pass

    result = None
    for attempt in range(3):
        try:
            if hasattr(broker, "async_send_order"):
                import asyncio
                result = await broker.async_send_order(mapped_symbol, stake, direction, duration)
            else:
                result = broker.send_order(mapped_symbol, stake, direction, duration)

            if result and result.get("status") == "ok":
                break

            if attempt < 2:
                err_msg = result.get("result", "") if result else "sem resposta"
                # "fechado" e de mercado/negocio — nao reconectar
                if any(kw in err_msg.lower() for kw in ["reconect", "conexao", "connect", "timeout"]) and "mercado fechado" not in err_msg.lower():
                    logger.warning(f"TV attempt {attempt+1}/3: {err_msg}. Reconectando...")
                    try:
                        broker.disconnect()
                    except Exception:
                        pass
                    await asyncio.sleep(3)
                    try:
                        broker = _create_broker(user.id, broker_name)
                        with _cache_lock:
                            key = _cache_key(user.id, broker_setting.id)
                            _broker_cache[key] = {"broker": broker, "created_at": time.time()}
                    except Exception as e2:
                        logger.error(f"Falha ao reconectar broker: {e2}")
                        return TradingViewWebhookResponse(
                            status="error",
                            message=f"Falha ao reconectar broker: {str(e2)}",
                        )
                    continue
            break
        except Exception as e:
            logger.error(f"Falha ao enviar ordem (attempt {attempt+1}/3): {e}")
            if attempt < 2:
                try:
                    broker.disconnect()
                except Exception:
                    pass
                await asyncio.sleep(3)
                try:
                    broker = _create_broker(user.id, broker_name)
                    with _cache_lock:
                        key = _cache_key(user.id, broker_setting.id)
                        _broker_cache[key] = {"broker": broker, "created_at": time.time()}
                except Exception as e2:
                    logger.error(f"Falha ao reconectar broker: {e2}")
            else:
                with _cache_lock:
                    key = _cache_key(user.id, broker_setting.id)
                    _broker_cache.pop(key, None)
                return TradingViewWebhookResponse(
                    status="error",
                    message=f"Falha ao enviar ordem: {str(e)}",
                )

    if not result or result.get("status") != "ok":
        return TradingViewWebhookResponse(
            status="rejected",
            message=f"Ordem recusada: {result.get('result') if result else 'sem resposta'}",
        )

    contract_id = result.get("contract_id") or result.get("order_id")

    audit_trade_id = None
    try:
        from src.services.audit_service import log_trade
        audit_trade_id = log_trade(
            user_id=user.id,
            broker_setting_id=broker_setting.id,
            symbol=mapped_symbol,
            direction=direction,
            stake=stake,
            duration=duration,
            status="pending",
            broker_trade_id=str(contract_id) if contract_id else None,
            notes=f"source=tradingview signal_symbol={symbol}",
        )
    except Exception:
        pass

    try:
        import json as _json
        from datetime import datetime as _dte
        ops_file = f"live_operations_{user.id}.json"
        ops = []
        if os.path.exists(ops_file):
            try:
                with open(ops_file, "r") as f:
                    ops = _json.load(f)
            except Exception:
                pass
        ops.append({
            "id": str(contract_id or _dte.now().strftime("%H%M%S%f")),
            "symbol": symbol,
            "mapped_symbol": mapped_symbol,
            "direction": direction,
            "result": "PENDENTE",
            "profit": 0,
            "stake": stake,
            "time": _dte.now().strftime("%H:%M:%S"),
            "date": _dte.now().strftime("%Y-%m-%d"),
        })
        today = _dte.now().strftime("%Y-%m-%d")
        ops = [o for o in ops if o.get("date") == today][-50:]
        with open(ops_file, "w") as f:
            _json.dump(ops, f)
    except Exception:
        pass

    trade_info = {
        "symbol": symbol,
        "mapped_symbol": mapped_symbol,
        "direction": direction,
        "stake": stake,
        "duration": duration,
        "contract_id": contract_id,
        "broker": broker_name,
        "timestamp": datetime.now().isoformat(),
        "audit_trade_id": audit_trade_id,
    }

    if broker_name in ("deriv", "deriv_demo", "deriv_real"):
        from src.broker.deriv import DerivBroker
        trade_info["duration"] = DerivBroker.DERIV_EXPIRATION_MINUTES

    t = threading.Thread(
        target=_wait_and_resolve,
        args=(user.id, broker, broker_setting.id, broker_name, session_manager, trade_info),
        daemon=True,
    )
    t.start()

    sm = session_manager.get_status()
    return TradingViewWebhookResponse(
        status="executed",
        message=f"Ordem enviada! {direction} {mapped_symbol} | Stake: ${stake:.2f}",
        stake=stake,
        direction=direction,
        symbol=mapped_symbol,
        session_info=sm,
    )


def _wait_and_resolve(user_id, broker, broker_setting_id, broker_name, session_manager, trade_info):
    """Espera resultado do trade e atualiza saldo/gerenciamento. Executa em thread separada."""
    import json
    from datetime import datetime

    try:
        _do_wait_and_resolve(user_id, broker, broker_setting_id, broker_name, session_manager, trade_info)
    except Exception as e:
        logger.error(f"[RESOLVE] Erro fatal na thread de resultado: {e}", exc_info=True)


def _do_wait_and_resolve(user_id, broker, broker_setting_id, broker_name, session_manager, trade_info):
    import json
    from datetime import datetime

    stake = trade_info["stake"]
    duration = trade_info["duration"]
    contract_id = trade_info.get("contract_id")
    mapped_symbol = trade_info["mapped_symbol"]

    wait_seconds = duration * 60 + 5
    logger.info(f"[RESOLVE] Aguardando resultado do trade em {mapped_symbol} por {wait_seconds}s...")
    time.sleep(wait_seconds)

    balance_after = None
    profit = -stake

    try:
        if broker_name == "iqoption" and hasattr(broker, "api"):
            try:
                balances = broker.api.get_balances()
                for b in (balances or []):
                    if b.get("id") == broker.api.backendapi_balance_id:
                        balance_after = float(b.get("amount", 0))
                        break
            except Exception:
                pass

            if balance_after is None:
                try:
                    balance_after = broker.api.get_balance()
                except Exception:
                    pass

            if balance_after and balance_after > 0:
                profit = balance_after - (session_manager.current_balance or session_manager.initial_balance)
                if profit > 0:
                    payout_pct = profit / stake if stake > 0 else 0.85
                    logger.info(f"[RESOLVE] WIN detectado por saldo: {profit:.2f} (payout ~{payout_pct:.0%})")
                elif profit < 0:
                    logger.info(f"[RESOLVE] LOSS detectado por saldo: {profit:.2f}")
                else:
                    profit = -stake
                    logger.info(f"[RESOLVE] Sem mudanca de saldo. Assumindo LOSS: -${stake:.2f}")
            else:
                logger.warning(f"[RESOLVE] Nao conseguiu obter saldo. Assumindo LOSS: -${stake:.2f}")

        elif broker_name in ("deriv", "deriv_demo", "deriv_real") and hasattr(broker, "get_contract_status"):
            try:
                status = broker.get_contract_status(contract_id)
                balance_after = broker.get_balance()
                if status and status.get("result") == "won":
                    profit = stake * 0.85
                elif status and status.get("result") == "lost":
                    profit = -stake
            except Exception as e:
                logger.warning(f"[RESOLVE] Erro ao consultar resultado Deriv: {e}")

    except Exception as e:
        logger.error(f"[RESOLVE] Erro ao verificar resultado: {e}")

    logger.info(
        f"[RESOLVE] TRADE COMPLETO: {trade_info['direction']} {mapped_symbol} | "
        f"Stake: ${stake:.2f} | Profit: ${profit:.2f} | "
        f"Saldo: ${session_manager.current_balance:.2f}"
    )

    session_manager.register_result(profit)

    if balance_after and balance_after > 0:
        session_manager.update_balance(balance_after)

    # ── Atualizar live_status.json para o dashboard ──
    try:
        sm_status = session_manager.get_status()
        result_label = "WIN" if profit > 0 else "LOSS" if profit < 0 else "EMPATE"
        live = {
            "broker": broker_name,
            "account_mode": "Demo",
            "initial_balance": round(session_manager.initial_balance, 2),
            "current_balance": round(session_manager.current_balance, 2),
            "profit": round(sm_status.get("daily_profit", 0), 2),
            "profit_pct": round((sm_status.get("daily_profit", 0) / session_manager.initial_balance * 100), 2) if session_manager.initial_balance > 0 else 0,
            "daily_target": round(sm_status.get("daily_target", 0), 2),
            "daily_profit": round(sm_status.get("daily_profit", 0), 2),
            "daily_progress_pct": round(sm_status.get("daily_progress_pct", 0), 2),
            "current_session": sm_status.get("current_session", 1),
            "session_entries_used": sm_status.get("session_entries_used", 0),
            "session_profit": round(sm_status.get("session_profit", 0), 2),
            "session_target": round(sm_status.get("session_target", 0), 2),
            "management_pct": 3.0,
            "current_stake": round(stake, 2),
            "signals_today": sm_status.get("total_trades", 0),
            "success_count": sm_status.get("wins", 0),
            "success_rate": sm_status.get("win_rate", 0),
            "gale_level": sm_status.get("gale_level", 0),
            "last_message": f"TV {result_label}: {trade_info['direction']} {mapped_symbol} | ${profit:+.2f}",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "meta_hit_today": session_manager.finished and sm_status.get("daily_profit", 0) >= sm_status.get("daily_target", 0),
            "auto_lock_meta": True,
            "meta_hit_date": None,
            "source": "tradingview",
        }
        with open(f"live_status_{user_id}.json", "w") as f:
            json.dump(live, f)

        ops = []
        ops_file = f"live_operations_{user_id}.json"
        try:
            with open(ops_file, "r") as f:
                ops = json.load(f)
        except Exception:
            pass
        op_id = str(contract_id or "")
        updated = False
        for op in reversed(ops):
            if op.get("id") == op_id or (op.get("mapped_symbol") == mapped_symbol and op.get("result") == "PENDENTE"):
                op["result"] = result_label
                op["profit"] = round(profit, 2)
                updated = True
                break
        if not updated:
            ops.append({
                "id": op_id,
                "symbol": trade_info.get("symbol", mapped_symbol),
                "mapped_symbol": mapped_symbol,
                "direction": trade_info["direction"],
                "result": result_label,
                "profit": round(profit, 2),
                "stake": stake,
                "time": datetime.now().strftime("%H:%M:%S"),
                "date": datetime.now().strftime("%Y-%m-%d"),
            })
        today = datetime.now().strftime("%Y-%m-%d")
        ops = [o for o in ops if o.get("date") == today][-50:]
        with open(ops_file, "w") as f:
            json.dump(ops, f)

    except Exception as e:
        logger.warning(f"[RESOLVE] Erro ao atualizar live_status.json: {e}")

    try:
        from src.database.session import SessionLocal
        db = SessionLocal()
        try:
            bs = db.query(BrokerSetting).filter(BrokerSetting.id == broker_setting_id).first()
            if bs:
                if balance_after and balance_after > 0:
                    bs.balance = balance_after

                if session_manager.finished and session_manager.daily_profit >= session_manager.daily_target:
                    bs.meta_hit_today = True
                    bs.meta_hit_date = datetime.now().strftime("%Y-%m-%d")
                    logger.info(f"[RESOLVE] Meta diaria atingida! Salvando bloqueio no broker {bs.broker_name}")

                db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[RESOLVE] Erro ao atualizar saldo/meta no DB: {e}")

    try:
        audit_id = trade_info.get("audit_trade_id")
        if audit_id:
            from src.services.audit_service import update_trade_result
            result_label = "won" if profit > 0 else "lost" if profit < 0 else "equal"
            update_trade_result(
                trade_id=audit_id,
                status="closed",
                result=result_label,
                profit_loss=round(profit, 2),
                balance_after=balance_after,
            )
    except Exception:
        pass

    try:
        logger.info(
            f"TRADE_RESULT user={user_id} symbol={mapped_symbol} "
            f"direction={trade_info['direction']} stake={stake:.2f} "
            f"profit={profit:.2f} balance={session_manager.current_balance:.2f}"
        )
    except Exception:
        pass
