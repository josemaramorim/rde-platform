"""
Trade executor — receives a signal, connects to the broker,
places the trade, and updates the user's cycle/profit.

Suporta:
  - Binary Options (IQ Option, Deriv, Quotex, Pocket Option): stake fixo, expiry fixo
  - Filtro de notícias econômicas (bloqueia trades em eventos de alto impacto)
"""
import time
import json
import os
import logging
import threading
from typing import Optional
from datetime import datetime
from src.broker.factory import get_broker
from src.services.management_3pct import SessionManager
from src.strategies.sniper import RDESniperStrategy
from src.services.news_filter import is_blocked_by_news, get_upcoming_high_impact

logger = logging.getLogger("rde")

FOREX_BROKERS = set()
BINARY_BROKERS = {"iqoption", "deriv", "quotex", "pocketoption"}

DEFAULT_SYMBOL = {
    "deriv": "R_100",
    "iqoption": "EURUSD-OTC",
}

_session_cache: dict = {}
_cache_lock = threading.Lock()


def _get_session_manager(user_id: int, balance: float, broker_name: str = ""):
    today = datetime.now().strftime("%Y-%m-%d")
    cache_key = f"{user_id}_{broker_name}"
    with _cache_lock:
        entry = _session_cache.get(cache_key)
        if entry:
            sm = entry["manager"]
            if entry.get("date") != today or entry.get("broker") != broker_name:
                sm = SessionManager(balance)
                _session_cache[cache_key] = {"manager": sm, "created_at": time.time(), "date": today, "broker": broker_name}
                return sm
            sm.update_balance(balance)
            return sm
    sm = SessionManager(balance)
    with _cache_lock:
        _session_cache[cache_key] = {"manager": sm, "created_at": time.time(), "date": today, "broker": broker_name}
    return sm


def _write_live_status(user_id, broker_name, session_manager, stake, last_message):
    try:
        sm = session_manager.get_status()
        live = {
            "broker": broker_name,
            "account_mode": "Real",
            "initial_balance": round(session_manager.initial_balance, 2),
            "current_balance": round(session_manager.current_balance, 2),
            "profit": round(sm.get("daily_profit", 0), 2),
            "profit_pct": round(
                (sm.get("daily_profit", 0) / session_manager.initial_balance * 100), 2
            ) if session_manager.initial_balance > 0 else 0,
            "daily_target": round(sm.get("daily_target", 0), 2),
            "daily_profit": round(sm.get("daily_profit", 0), 2),
            "daily_progress_pct": round(sm.get("daily_progress_pct", 0), 2),
            "current_session": sm.get("current_session", 1),
            "session_entries_used": sm.get("session_entries_used", 0),
            "session_profit": round(sm.get("session_profit", 0), 2),
            "session_target": round(sm.get("session_target", 0), 2),
            "current_stake": round(stake, 2),
            "signals_today": sm.get("total_trades", 0),
            "success_count": sm.get("wins", 0),
            "success_rate": sm.get("win_rate", 0),
            "gale_level": sm.get("gale_level", 0),
            "last_message": last_message,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "meta_hit_today": False,
            "auto_lock_meta": False,
            "source": "signal",
        }
        with open(f"live_status_{user_id}.json", "w") as f:
            json.dump(live, f)
    except Exception:
        pass


def execute_trade(user, signal: str, db,
                  symbol: Optional[str] = None,
                  sl_points: Optional[int] = None,
                  tp_points: Optional[int] = None) -> dict:
    broker = None
    try:
        news_block = is_blocked_by_news(minutes_before=15, minutes_after=10)
        if news_block:
            logger.warning(
                f"Trade BLOQUEADO para {user.email}: {news_block['reason']} "
                f"(evento em {news_block['minutes_away']} min)"
            )
            return {
                "outcome": "blocked",
                "profit_delta": 0,
                "reason": news_block["reason"],
                "event": news_block["event_title"],
                "minutes_away": news_block["minutes_away"],
            }

        broker = get_broker(user, db=db)
        balance = broker.get_balance()
        broker_name = (user.broker or "").lower()
        symbol = symbol or DEFAULT_SYMBOL.get(broker_name, "EURUSD")

        session = _get_session_manager(user.id, balance, broker_name)

        if not session.can_trade():
            sm = session.get_status()
            msg = f"Sessoes concluidas. Lucro do dia: ${sm['daily_profit']:.2f}"
            logger.info(f"Trade BLOQUEADO para {user.email}: {msg}")
            _write_live_status(user.id, broker_name, session, session.stake, msg)
            return {
                "outcome": "blocked",
                "profit_delta": 0,
                "reason": msg,
            }

        stake = session.stake

        strategy = RDESniperStrategy()
        result = None

        if broker_name in FOREX_BROKERS:
            lot = broker._stake_to_lot(stake, symbol) if hasattr(broker, '_stake_to_lot') else round(stake / 1000, 2)

            if sl_points is None:
                sl_points = 20
            if tp_points is None:
                tp_points = 40

            result = broker.send_order(
                symbol=symbol,
                stake=stake,
                direction=signal,
                sl_points=sl_points,
                tp_points=tp_points,
            )

            if result.get("status") == "ok":
                order_id = result.get("order_id")
                logger.info(
                    f"FOREX {signal.upper()} {symbol} lot={lot} "
                    f"SL={sl_points}pts TP={tp_points}pts balance=${balance:.2f}"
                )
                profit_delta = 0.0
                if order_id:
                    time.sleep(2)
                    pos_info = broker.get_open_positions() if hasattr(broker, 'get_open_positions') else []
                    for p in pos_info:
                        if p.get("ticket") == order_id:
                            profit_delta = float(p.get("profit", 0))
                            break
                outcome = "win" if profit_delta >= 0 else "loss"
                session.register_result(profit_delta)
                session.update_balance(balance + profit_delta)
                _write_live_status(
                    user.id, broker_name, session, stake,
                    f"FOREX {signal.upper()} {symbol} | ${profit_delta:+.2f}"
                )
                return {
                    "outcome": outcome,
                    "profit_delta": profit_delta,
                    "stake": stake,
                    "lot": lot,
                    "symbol": symbol,
                    "sl": sl_points,
                    "tp": tp_points,
                    "balance": balance,
                    "total_profit": getattr(user, "total_profit", 0) + profit_delta,
                    "broker_response": result,
                }
            else:
                outcome = "error"
                profit_delta = 0
                session.register_result(0)
                _write_live_status(user.id, broker_name, session, stake, f"FOREX ordem rejeitada: {result.get('result')}")
        else:
            result = broker.send_order(
                symbol=symbol,
                stake=stake,
                direction=signal,
            )

            if result.get("status") != "ok":
                logger.error(f"Ordem rejeitada pela corretora: {result.get('result')}")
                outcome = "error"
                profit_delta = 0
                session.register_result(0)
                _write_live_status(user.id, broker_name, session, stake, f"Ordem rejeitada: {result.get('result')}")
            else:
                contract_id = result.get("contract_id") or result.get("order_id")
                logger.info(
                    f"BINARY {signal.upper()} {symbol} stake=${stake} "
                    f"({stake/balance*100:.1f}% do saldo ${balance:.2f}). "
                    f"Aguardando expiracao..."
                )

                deadline = time.time() + 90
                trade_status = "error"
                while time.time() < deadline:
                    time.sleep(5)
                    try:
                        trade_status = broker.get_contract_status(contract_id)
                        if trade_status in ("won", "lost"):
                            break
                    except Exception:
                        continue
                outcome = "win" if trade_status == "won" else "loss"
                profit_delta = float(stake * 0.85 if outcome == "win" else -stake)
                session.register_result(profit_delta)
                session.update_balance(balance + profit_delta)
                _write_live_status(
                    user.id, broker_name, session, stake,
                    f"{'WIN' if outcome == 'win' else 'LOSS'}! {signal.upper()} {symbol} | ${profit_delta:+.2f}"
                )

        if hasattr(user, "total_profit") and user.total_profit:
            user.total_profit = round(float(user.total_profit) + profit_delta, 2)

        logger.info(
            f"TRADE user={user.email} broker={broker_name} signal={signal} "
            f"balance=${balance:.2f} stake=${stake} outcome={outcome} "
            f"profit_delta=${profit_delta:+.2f} total_profit=${getattr(user, 'total_profit', 0)}"
        )

        return {
            "outcome": outcome,
            "profit_delta": profit_delta,
            "stake": stake,
            "balance": balance,
            "total_profit": getattr(user, "total_profit", 0),
            "broker_response": result,
        }

    except Exception as exc:
        logger.error(f"execute_trade error for user={user.email}: {exc}")
        return {"outcome": "error", "error": str(exc)}

    finally:
        if broker:
            try:
                broker.disconnect()
            except Exception:
                pass
