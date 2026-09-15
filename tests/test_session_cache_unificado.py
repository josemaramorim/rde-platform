"""Testes da fonte única de SessionManager (IMP-007, spec 009).

Antes desta correcao, src/routes/tradingview_bridge.py e src/executor.py
mantinham cada um seu proprio dicionario de cache (copia quase identica da
mesma funcao) -- um usuario disparando sinal pelo TradingView e pelo
endpoint manual POST /signal (Celery -> executor.py) tinha 2 SessionManager
independentes, podendo efetivamente dobrar o limite de risco diario.

Estes testes travam que os dois modulos agora enxergam o MESMO
SessionManager para o mesmo user_id + broker_name.
"""
import src.executor as ex
import src.routes.tradingview_bridge as tv
from src.services.management_3pct import _session_cache, get_session_manager


def setup_function():
    """Cada teste comeca com o cache global limpo (estado compartilhado entre testes)."""
    _session_cache.clear()


def test_tradingview_bridge_e_executor_compartilham_a_mesma_instancia():
    sm_via_tv = tv._get_session_manager("user-x", 100.0, "deriv")
    sm_via_executor = ex._get_session_manager("user-x", 100.0, "deriv")

    assert sm_via_tv is sm_via_executor


def test_resultado_registrado_por_um_fluxo_e_visto_pelo_outro():
    """O cerne do bug original: sinal via TradingView afeta o ciclo de risco
    que o endpoint manual (executor.py) tambem consulta."""
    sm = tv._get_session_manager("user-y", 100.0, "iqoption")
    sm.register_result(-5.0)  # sinal "via TradingView"

    sm_de_novo = ex._get_session_manager("user-y", 100.0, "iqoption")

    assert sm_de_novo.daily_profit == -5.0
    assert sm_de_novo.session_entries_used == 1


def test_usuarios_diferentes_nao_compartilham_sessao():
    sm_a = get_session_manager("user-a", 100.0, "iqoption")
    sm_b = get_session_manager("user-b", 100.0, "iqoption")
    assert sm_a is not sm_b


def test_corretoras_diferentes_do_mesmo_usuario_nao_compartilham_sessao():
    sm_iq = get_session_manager("user-z", 100.0, "iqoption")
    sm_deriv = get_session_manager("user-z", 100.0, "deriv")
    assert sm_iq is not sm_deriv
