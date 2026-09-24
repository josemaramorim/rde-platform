"""Testes de src/telegram_copier.py::execute_trade — payout real (IMP-005, spec 006).

Antes desta correcao, uma operacao vencedora sempre registrava
profit = stake * 0.85 (percentual fixo), independente do que a corretora
realmente pagou. Estes testes travam o calculo pela variacao real de saldo,
incluindo o fallback seguro quando o saldo ainda nao reflete o ganho.
"""
import pytest

import src.telegram_copier as tc
from src.services.management_3pct import SessionManager


class _FakeBroker:
    """Simula send_order/get_contract_status/get_balance de um broker qualquer."""

    def __init__(self, balance_after, trade_status="won"):
        self._balance_after = balance_after
        self._trade_status = trade_status

    def send_order(self, symbol, stake, direction, duration=1):
        return {"status": "ok", "contract_id": "c1"}

    def get_contract_status(self, contract_id):
        return self._trade_status

    def get_balance(self):
        return self._balance_after


def _make_copier(broker, balance=100.0):
    copier = tc.TelegramCopier(user_id="u1", broker_name="iqoption")
    copier.is_running = True
    copier.session_manager = SessionManager(balance)
    copier.current_balance = balance
    copier.initial_balance = balance
    copier.stop_loss_pct = 0.5
    copier.broker = broker
    return copier


@pytest.fixture(autouse=True)
def _sem_espera_real(monkeypatch):
    """asyncio.sleep(duration*60+3) tornaria o teste lento -- acelera sem pular a logica."""
    async def _fast_sleep(_seconds):
        pass
    monkeypatch.setattr(tc.asyncio, "sleep", _fast_sleep)


@pytest.fixture(autouse=True)
def _sem_cliente_telegram_real(monkeypatch):
    """TelegramCopier cria um TelethonClient no construtor: exige TELEGRAM_API_ID/HASH
    reais (ausentes no CI) e grava um .session na raiz do repo. Nenhum teste
    daqui usa o Telegram."""
    class _FakeTelegramClient:
        def __init__(self, *args, **kwargs):
            pass
    monkeypatch.setattr(tc, "TelegramClient", _FakeTelegramClient)


async def test_win_com_payout_real_nao_fixo():
    # stake = 1% de 100 = 1.00; saldo 100 -> 100.87 = payout real de 87%
    broker = _FakeBroker(balance_after=100.87)
    copier = _make_copier(broker, balance=100.0)

    await copier.execute_trade({"symbol": "EURUSD-OTC", "direction": "CALL", "duration": 1})

    status = copier.session_manager.get_status()
    assert status["daily_profit"] == pytest.approx(0.87)


async def test_win_com_delta_absurdo_e_limitado(caplog):
    """Spec 019: delta > 2x o stake indica credito atrasado de ordem anterior
    somado ao desta -- o lucro registrado e limitado a 95% do stake."""
    broker = _FakeBroker(balance_after=109.2)  # +9.2 num stake de 1.00 (920%)
    copier = _make_copier(broker, balance=100.0)

    await copier.execute_trade({"symbol": "EURUSD-OTC", "direction": "CALL", "duration": 1})

    status = copier.session_manager.get_status()
    assert status["daily_profit"] == pytest.approx(0.95)
    assert "muito acima do payout esperado" in caplog.text


async def test_loss_permanece_perda_total_do_stake():
    broker = _FakeBroker(balance_after=100.0, trade_status="lost")
    copier = _make_copier(broker, balance=100.0)

    await copier.execute_trade({"symbol": "EURUSD-OTC", "direction": "CALL", "duration": 1})

    status = copier.session_manager.get_status()
    assert status["daily_profit"] == pytest.approx(-1.0)  # stake padrao da sessao


async def test_win_com_saldo_nao_atualizado_usa_fallback_seguro():
    """Saldo nunca reflete o ganho (mesmo apos o retry) -- nunca inventa payout,
    nunca fica negativo para um WIN confirmado."""
    broker = _FakeBroker(balance_after=100.0, trade_status="won")  # saldo nao mudou
    copier = _make_copier(broker, balance=100.0)

    await copier.execute_trade({"symbol": "EURUSD-OTC", "direction": "CALL", "duration": 1})

    status = copier.session_manager.get_status()
    assert status["daily_profit"] == pytest.approx(0.0)
