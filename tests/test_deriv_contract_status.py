"""Testes de src/broker/deriv.py::_get_contract_status_async (IMP-009, spec 008).

Antes desta correcao, a funcao tinha um `await asyncio.sleep(62)` fixo antes
de consultar o status -- sem relacao com o timeframe do sinal, e causa raiz
de um timeout que fazia trades Deriv via executor.py virarem LOSS registrado
(ver tests/test_executor_payout.py). Este teste trava que a consulta agora
acontece imediatamente, sem espera interna.
"""
import time

from src.broker.deriv import DerivBroker


async def test_get_contract_status_nao_espera_mais_62s(monkeypatch):
    broker = DerivBroker(api_token="fake-token")

    async def _fake_ws_request(payload, timeout=30.0):
        return {"proposal_open_contract": {"status": "won"}}

    monkeypatch.setattr(broker, "_ws_request", _fake_ws_request)

    start = time.monotonic()
    status = await broker._get_contract_status_async("123")
    elapsed = time.monotonic() - start

    assert status == "won"
    assert elapsed < 1.0, f"esperado retorno imediato, levou {elapsed:.1f}s (sleep(62) ainda presente?)"
