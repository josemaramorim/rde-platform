"""Testes de src/broker/deriv_symbols.py::resolve_deriv_symbol (IMP-003, spec 003).

Antes desta correcao, um simbolo sem match confiavel virava um palpite por
prefixo ou um default fixo em "R_100" -- ordem real podia ser executada num
ativo sem relacao com o sinal. Estes testes travam o comportamento correto:
descartar (retornar None) em vez de adivinhar.
"""
from src.broker.deriv_symbols import resolve_deriv_symbol


def test_match_exato_no_mapa_canonico():
    assert resolve_deriv_symbol("EURUSD") == "R_100"
    assert resolve_deriv_symbol("GBPUSD") == "R_75"


def test_match_apos_remover_otc():
    assert resolve_deriv_symbol("EURUSD-OTC") == "R_100"
    assert resolve_deriv_symbol("EURUSD_OTC") == "R_100"


def test_passthrough_de_simbolo_deriv_ja_valido():
    assert resolve_deriv_symbol("R_75") == "R_75"
    assert resolve_deriv_symbol("CRASH500") == "CRASH500"
    assert resolve_deriv_symbol("1HZ50V") == "1HZ50V"


def test_simbolo_desconhecido_e_descartado_nao_adivinhado():
    assert resolve_deriv_symbol("XPTOZZZ") is None


def test_quase_match_nao_cai_mais_no_fallback_por_prefixo():
    """Antes do fix, "EURUSDX" batia em sym.startswith("EURUSD") e virava R_100
    silenciosamente. Agora precisa ser descartado -- nao e um alias confirmado."""
    assert resolve_deriv_symbol("EURUSDX") is None
