"""Testes de src/plans_catalog.py — fonte única de plano->corretoras (IMP-004, spec 001)."""
import json

from src.plans_catalog import (
    PLAN_CATALOG,
    VALID_BROKERS,
    allowed_brokers_for_plan,
    allowed_brokers_json,
    plan_seed_kwargs,
)


def test_regra_canonica():
    """Free so IQ Option; Pro soma Deriv; VIP libera todas (commit 975d576)."""
    assert allowed_brokers_for_plan("Free") == ["iqoption"]
    assert allowed_brokers_for_plan("Pro") == ["iqoption", "deriv"]
    assert allowed_brokers_for_plan("VIP") == ["iqoption", "deriv", "quotex", "pocketoption"]


def test_case_insensitive():
    assert allowed_brokers_for_plan("free") == allowed_brokers_for_plan("Free")
    assert allowed_brokers_for_plan("FREE") == allowed_brokers_for_plan("Free")
    assert allowed_brokers_for_plan("vip") == allowed_brokers_for_plan("VIP")


def test_plano_desconhecido_retorna_lista_vazia():
    assert allowed_brokers_for_plan("Enterprise") == []
    assert allowed_brokers_for_plan("") == []


def test_allowed_brokers_json_serializa_a_mesma_lista():
    assert json.loads(allowed_brokers_json("Pro")) == ["iqoption", "deriv"]
    assert allowed_brokers_json("Enterprise") == "[]"


def test_plan_seed_kwargs_tem_o_formato_esperado():
    kwargs = plan_seed_kwargs("VIP")
    assert kwargs["name"] == "VIP"
    assert kwargs["max_signals_per_day"] == 99999
    assert kwargs["max_stake"] == 1000.0
    assert kwargs["price_usd"] == 49.0
    assert kwargs["is_demo"] is False
    # allowed_brokers persiste como JSON string (coluna Text no banco), nao lista.
    assert isinstance(kwargs["allowed_brokers"], str)
    assert json.loads(kwargs["allowed_brokers"]) == ["iqoption", "deriv", "quotex", "pocketoption"]


def test_valid_brokers_cobre_as_4_corretoras_suportadas():
    assert VALID_BROKERS == {"iqoption", "deriv", "quotex", "pocketoption"}


def test_plan_catalog_tem_exatamente_os_3_planos():
    assert set(PLAN_CATALOG.keys()) == {"Free", "Pro", "VIP"}
