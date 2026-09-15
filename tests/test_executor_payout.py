"""Testes de src/executor.py::execute_trade — payout real (IMP-005, spec 006)
e timeout real da Deriv (IMP-009, spec 008).

Cobre tanto o payout fixo de 85% (corrigido na spec 006) quanto o loop de
polling generico que nao funcionava pra Deriv: get_contract_status() da
Deriv bloqueava 62s por dentro, e o orcamento de 90s do loop estourava
antes do contrato (180s fixos) sequer expirar -- todo trade Deriv virava
LOSS registrado por timeout (spec 008).
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


class _FakeDerivBroker:
    """Simula a Deriv: get_contract_status() nunca resolveria a tempo no loop
    generico antigo (nao e nem chamado pelo branch Deriv de execute_trade)."""

    def __init__(self, balance_before, balance_after):
        self._before = balance_before
        self._after = balance_after
        self._calls = 0

    def get_balance(self):
        self._calls += 1
        return self._before if self._calls == 1 else self._after

    def send_order(self, symbol, stake, direction):
        return {"status": "ok", "contract_id": "c1"}

    def get_contract_status(self, contract_id):
        # Nao deveria nem ser chamado pro branch Deriv -- se for, e um sinal
        # de regressao (voltou a depender do loop de polling generico).
        raise AssertionError("get_contract_status nao deveria ser chamado para Deriv (IMP-009)")


class _FakeUser:
    id = "u1"
    email = "teste@teste.com"
    broker = "iqoption"


class _FakeDerivUser:
    id = "u2"
    email = "teste-deriv@teste.com"
    broker = "deriv"


@pytest.fixture(autouse=True)
def _sem_espera_real(monkeypatch):
    monkeypatch.setattr(ex.time, "sleep", lambda s: None)
    monkeypatch.setattr(ex, "is_blocked_by_news", lambda **kwargs: None)
    monkeypatch.setattr(ex, "_write_live_status", lambda *a, **k: None)


def _run(monkeypatch, broker, session, user=None):
    monkeypatch.setattr(ex, "_get_session_manager", lambda user_id, balance, broker_name="": session)
    monkeypatch.setattr(ex, "get_broker", lambda user, db=None: broker)
    return ex.execute_trade(user or _FakeUser(), "call", db=None, symbol="EURUSD-OTC")


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


def test_deriv_win_nao_depende_mais_de_get_contract_status(monkeypatch):
    """Antes (IMP-009): get_contract_status() da Deriv bloqueava 62s por
    dentro, o loop de polling de 90s estourava antes do contrato expirar, e
    o trade virava LOSS por timeout mesmo tendo ganhado de verdade."""
    broker = _FakeDerivBroker(balance_before=200.0, balance_after=217.6)
    session = _FakeSessionManager(200.0)

    result = _run(monkeypatch, broker, session, user=_FakeDerivUser())

    assert result["outcome"] == "win"
    assert result["profit_delta"] == pytest.approx(17.6)


def test_deriv_loss_real_via_variacao_de_saldo(monkeypatch):
    broker = _FakeDerivBroker(balance_before=200.0, balance_after=195.0)
    session = _FakeSessionManager(200.0)

    result = _run(monkeypatch, broker, session, user=_FakeDerivUser())

    assert result["outcome"] == "loss"
    assert result["profit_delta"] == pytest.approx(-session.stake)
