"""Testes de src/routes/tradingview_bridge.py::_do_wait_and_resolve (IMP-005, spec 006).

Antes desta correcao, o branch da Deriv comparava
broker.get_contract_status() (retorna STRING "won"/"lost") com .get("result")
(metodo de dict) -- sempre lancava AttributeError, silenciado pelo except, e
todo trade Deriv virava LOSS registrado independente do resultado real.
Quotex/Pocket Option nem tinham branch -- mesmo problema.

Estes testes travam o comportamento correto: profit calculado pela variacao
real de saldo, para Deriv e para o branch generico (Quotex/Pocket Option).
"""
import src.routes.tradingview_bridge as tv

TRADE_INFO = {
    "stake": 10.0,
    "duration": 1,
    "contract_id": "c1",
    "mapped_symbol": "R_100",
    "direction": "CALL",
}


class _FakeSessionManager:
    def __init__(self, balance):
        self.current_balance = balance
        self.initial_balance = balance
        self.last_profit = None

    def register_result(self, profit):
        self.last_profit = profit

    def update_balance(self, balance):
        self.current_balance = balance

    def get_status(self):
        return {
            "daily_profit": 0, "current_session": 1, "session_entries_used": 0,
            "session_profit": 0, "session_target": 0, "daily_target": 0,
            "daily_progress_pct": 0, "total_trades": 0, "wins": 0,
        }


class _FakeBroker:
    def __init__(self, balance_after):
        self._balance_after = balance_after

    def get_balance(self):
        return self._balance_after


def _resolve(broker_name, balance_after, balance_before=100.0):
    sm = _FakeSessionManager(balance_before)
    broker = _FakeBroker(balance_after)
    tv._do_wait_and_resolve("user1", broker, "setting1", broker_name, sm, dict(TRADE_INFO))
    return sm.last_profit


def test_deriv_win_real_via_variacao_de_saldo(monkeypatch):
    monkeypatch.setattr(tv.time, "sleep", lambda s: None)
    profit = _resolve("deriv", balance_after=108.5)
    assert profit == 8.5


def test_deriv_loss_real_via_variacao_de_saldo(monkeypatch):
    monkeypatch.setattr(tv.time, "sleep", lambda s: None)
    profit = _resolve("deriv", balance_after=90.0)
    assert profit == -10.0


def test_quotex_win_agora_resolve_corretamente(monkeypatch):
    """Antes: sem branch para quotex, caia sempre no default profit = -stake."""
    monkeypatch.setattr(tv.time, "sleep", lambda s: None)
    profit = _resolve("quotex", balance_after=105.0)
    assert profit == 5.0


def test_pocketoption_win_agora_resolve_corretamente(monkeypatch):
    monkeypatch.setattr(tv.time, "sleep", lambda s: None)
    profit = _resolve("pocketoption", balance_after=103.0)
    assert profit == 3.0
