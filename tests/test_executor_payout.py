"""Testes de src/executor.py::execute_trade — payout real (IMP-005, spec 006).

Mesma correcao da spec 006 aplicada ao terceiro fluxo de execucao
duplicado (Celery/executor.py): profit_delta calculado pela variacao real de
saldo, nao stake * 0.85 fixo.
"""
import pytest

import src.executor as ex


class _FakeSessionManager:
    def __init__(self, balance):
        self.stake = 5.0
        self.current_balance = balance
        self.last_profit = None

    def can_trade(self):
        return True

    def get_status(self):
        return {"daily_profit": 0}

    def register_result(self, profit):
        self.last_profit = profit

    def update_balance(self, balance):
        self.current_balance = balance


class _FakeBroker:
    """get_balance() retorna o saldo ANTES na 1a chamada e DEPOIS na 2a."""

    def __init__(self, balance_before, balance_after, trade_status="won"):
        self._before = balance_before
        self._after = balance_after
        self._trade_status = trade_status
        self._calls = 0

    def get_balance(self):
        self._calls += 1
        return self._before if self._calls == 1 else self._after

    def send_order(self, symbol, stake, direction):
        return {"status": "ok", "contract_id": "c1"}

    def get_contract_status(self, contract_id):
        return self._trade_status


class _FakeUser:
    id = "u1"
    email = "teste@teste.com"
    broker = "iqoption"


@pytest.fixture(autouse=True)
def _sem_espera_real(monkeypatch):
    monkeypatch.setattr(ex.time, "sleep", lambda s: None)
    monkeypatch.setattr(ex, "is_blocked_by_news", lambda **kwargs: None)
    monkeypatch.setattr(ex, "_write_live_status", lambda *a, **k: None)


def _run(monkeypatch, broker, session):
    monkeypatch.setattr(ex, "_get_session_manager", lambda user_id, balance, broker_name="": session)
    monkeypatch.setattr(ex, "get_broker", lambda user, db=None: broker)
    return ex.execute_trade(_FakeUser(), "call", db=None, symbol="EURUSD-OTC")


def test_win_com_payout_real_nao_fixo(monkeypatch):
    broker = _FakeBroker(balance_before=200.0, balance_after=217.6, trade_status="won")
    session = _FakeSessionManager(200.0)

    result = _run(monkeypatch, broker, session)

    assert result["outcome"] == "win"
    assert result["profit_delta"] == pytest.approx(17.6)


def test_loss_permanece_perda_total_do_stake(monkeypatch):
    broker = _FakeBroker(balance_before=200.0, balance_after=195.0, trade_status="lost")
    session = _FakeSessionManager(200.0)

    result = _run(monkeypatch, broker, session)

    assert result["outcome"] == "loss"
    assert result["profit_delta"] == pytest.approx(-session.stake)


def test_win_com_saldo_nao_atualizado_usa_fallback_seguro(monkeypatch):
    broker = _FakeBroker(balance_before=200.0, balance_after=200.0, trade_status="won")
    session = _FakeSessionManager(200.0)

    result = _run(monkeypatch, broker, session)

    assert result["outcome"] == "win"
    assert result["profit_delta"] == pytest.approx(0.0)
