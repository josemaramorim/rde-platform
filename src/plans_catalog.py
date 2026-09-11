"""Fonte única de verdade para o catálogo de planos (limites e corretoras liberadas).

Resolve IMP-004 (docs/sdd/IMPEDIMENTOS.md): a regra "plano -> corretoras liberadas"
estava duplicada e divergente em src/seed_plans.py, src/main.py (seed de startup),
src/routes/admin_routes.py (_PLAN_BROKER_RULES) e src/corrigir_admin.py — este
último chegou a liberar Deriv para o plano Free e todas as corretoras para o Pro.
Ver docs/sdd/specs/001-plan-brokers-fonte-unica.md.

Qualquer seed, correção ou validação de plano deve importar deste módulo —
nunca redeclarar a lista de corretoras (ou os demais defaults de plano) em
outro arquivo.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

# Corretoras suportadas pela plataforma (usado para validar entrada de admin).
VALID_BROKERS: frozenset[str] = frozenset({"iqoption", "deriv", "quotex", "pocketoption"})


@dataclass(frozen=True)
class PlanDefaults:
    name: str
    max_signals_per_day: int
    max_stake: float
    price_usd: float
    is_demo: bool
    allowed_brokers: list[str] = field(default_factory=list)


# Regra canônica: Free só IQ Option; Pro soma Deriv; VIP libera todas.
PLAN_CATALOG: dict[str, PlanDefaults] = {
    "Free": PlanDefaults(
        name="Free",
        max_signals_per_day=5,
        max_stake=5.0,
        price_usd=0.0,
        is_demo=True,
        allowed_brokers=["iqoption"],
    ),
    "Pro": PlanDefaults(
        name="Pro",
        max_signals_per_day=100,
        max_stake=100.0,
        price_usd=19.0,
        is_demo=False,
        allowed_brokers=["iqoption", "deriv"],
    ),
    "VIP": PlanDefaults(
        name="VIP",
        max_signals_per_day=99999,
        max_stake=1000.0,
        price_usd=49.0,
        is_demo=False,
        allowed_brokers=["iqoption", "deriv", "quotex", "pocketoption"],
    ),
}


def allowed_brokers_for_plan(plan_name: str) -> list[str]:
    """Corretoras liberadas para um plano, por nome (case-insensitive).

    Retorna [] para um nome de plano desconhecido, em vez de lançar — quem
    chama decide se isso é um erro (ex.: 404) ou um "sem corretoras".
    """
    for key, defaults in PLAN_CATALOG.items():
        if key.lower() == plan_name.lower():
            return list(defaults.allowed_brokers)
    return []


def allowed_brokers_json(plan_name: str) -> str:
    """`allowed_brokers_for_plan` já serializado — `Plan.allowed_brokers` é armazenado como Text/JSON."""
    return json.dumps(allowed_brokers_for_plan(plan_name))


def plan_seed_kwargs(plan_name: str) -> dict:
    """Kwargs prontos para `Plan(**plan_seed_kwargs(...))` ou para comparar contra um registro existente."""
    d = PLAN_CATALOG[plan_name]
    return {
        "name": d.name,
        "max_signals_per_day": d.max_signals_per_day,
        "max_stake": d.max_stake,
        "price_usd": d.price_usd,
        "is_demo": d.is_demo,
        "allowed_brokers": json.dumps(d.allowed_brokers),
    }
