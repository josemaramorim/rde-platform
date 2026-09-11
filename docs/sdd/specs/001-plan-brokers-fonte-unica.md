# 001 — Fonte única para o catálogo de planos (plano → corretoras)

- **Status:** Em revisão
- **Autor:** josemaramorim (via Claude)
- **Data:** 2026-09-10
- **Impedimento(s) relacionado(s):** IMP-004 (`docs/sdd/IMPEDIMENTOS.md`). Encosta em IMP-011 (endpoint band-aid) e IMP-010 (`main.py` god file).
- **Zona de alto risco?** Não — não toca `src/broker/*`, `src/telegram_copier.py`, `src/routes/tradingview_bridge.py` nem `src/executor.py`. Mesmo assim exige autorização explícita antes da implementação (Constituição §7).

## Problema

A regra de negócio "quais corretoras cada plano libera" (e os demais defaults de plano) está **hardcoded em 4 lugares**, e um deles diverge dos outros três:

| Fonte | Free | Pro | VIP |
|---|---|---|---|
| `src/seed_plans.py:14-18` | `["iqoption"]` | `["iqoption","deriv"]` | `["iqoption","deriv","quotex","pocketoption"]` |
| `src/main.py:999-1001` (seed no startup) | `["iqoption"]` | `["iqoption","deriv"]` | `["iqoption","deriv","quotex","pocketoption"]` |
| `src/routes/admin_routes.py:259-262` (`_PLAN_BROKER_RULES`) | `["iqoption"]` | `["iqoption","deriv"]` | `["iqoption","deriv","quotex","pocketoption"]` |
| `src/corrigir_admin.py:19-24` | **`["iqoption","deriv"]`** | **`["iqoption","deriv","quotex","pocketoption"]`** | `["iqoption","quotex","pocketoption","deriv"]` |

Consequência concreta: se `python -m src.corrigir_admin` roda por último, um usuário **Free passa a ter Deriv** e um usuário **Pro passa a ter todas as 4 corretoras** — entitlement acima do plano pago. Qual regra vale em produção depende de qual script rodou por último. Essa é a causa raiz do endpoint manual `POST /admin/v2/fix-plan-brokers` (`src/routes/admin_routes.py:266`), que existe só para "consertar na mão" o que os seeders bagunçam.

Além das corretoras, os outros campos de plano (`max_signals_per_day`, `max_stake`, `price_usd`, `is_demo`) também estão triplicados entre `seed_plans.py`, `main.py` e `corrigir_admin.py` — hoje coincidem, mas sem fonte única vão divergir do mesmo jeito.

Defeito adjacente no mesmo tema: `Plan.get_allowed_brokers()` está **definido duas vezes** em `src/models/user.py:127` e `:137` (Python usa silenciosamente a segunda). Viola Constituição §4 ("nenhuma duplicação de método dentro do mesmo arquivo").

## Contexto

A regra canônica pretendida é a que **3 das 4 fontes já usam** e que o commit `975d576` ("regras de corretoras por plano - Free(IQ), Pro(IQ+Deriv), VIP(todos)") documenta como intencional:

- **Free:** `iqoption`
- **Pro:** `iqoption`, `deriv`
- **VIP:** `iqoption`, `deriv`, `quotex`, `pocketoption`

O runtime **não** lê nenhuma dessas 4 constantes: a checagem de entitlement em `src/routes/broker.py:125-126,256-257` e `src/routes/user.py:113,141-143` lê `plan.allowed_brokers` **do banco**. Ou seja, as 4 constantes só importam no momento de *escrever* o plano (seed inicial e correção). Basta ter uma fonte única para essa escrita.

`src/main.py` é god file (IMP-010) — a edição aqui deve ser mínima: trocar o literal do seed por uma chamada ao módulo canônico, nada além disso.

## Proposta

### 1. Novo módulo canônico — `src/plans_catalog.py`

Fonte única, sem I/O, com type hints:

- `PLAN_CATALOG: dict[str, PlanDefaults]` para as chaves `"Free"`, `"Pro"`, `"VIP"`, cada uma com: `max_signals_per_day`, `max_stake`, `price_usd`, `is_demo`, `allowed_brokers: list[str]`.
- `VALID_BROKERS: frozenset[str]` = `{"iqoption", "deriv", "quotex", "pocketoption"}` (hoje repetido em `admin_routes.py:240`).
- `allowed_brokers_for_plan(name: str) -> list[str]` — case-insensitive; retorna `[]` para plano desconhecido (sem lançar).
- `allowed_brokers_json(name: str) -> str` — helper que devolve o JSON string, já que o modelo persiste `allowed_brokers` como `Text`.

Valores = a regra canônica da seção Contexto.

### 2. Consumidores passam a importar do módulo

- `src/seed_plans.py` — remove `PLAN_BROKERS`; monta a lista de planos a partir de `PLAN_CATALOG`.
- `src/main.py:~999-1001` — troca os 3 literais por iteração sobre `PLAN_CATALOG` (mudança localizada, sem mexer no resto da função de seed).
- `src/routes/admin_routes.py` — remove `_PLAN_BROKER_RULES` (linhas 259-262) e o set literal `valid` (linha 240); ambos passam a vir de `src/plans_catalog.py`. `POST /admin/v2/fix-plan-brokers` continua existindo, mas agora ressincroniza o banco **a partir da fonte única** (deixa de ser band-aid divergente e vira ferramenta legítima de re-seed).
- `src/corrigir_admin.py` — remove o `PLANS` local divergente; usa `PLAN_CATALOG`. Isso corrige a divergência Free/Pro.

### 3. Limpeza pontual em `src/models/user.py`

- Remover a primeira definição de `get_allowed_brokers` (linhas 127-135), mantendo uma só.

### Arquivos tocados

- `src/plans_catalog.py` (novo)
- `src/seed_plans.py`
- `src/main.py` (bloco de seed, edição mínima)
- `src/routes/admin_routes.py`
- `src/corrigir_admin.py`
- `src/models/user.py` (dedup de método)

Sem migração de schema. Sem mudança em nenhum arquivo da zona de alto risco.

## Critérios de aceite

- [ ] Existe exatamente **uma** definição da regra plano→corretoras no código (`src/plans_catalog.py`); `grep -rn '"iqoption"' src/` não encontra mais nenhuma lista de brokers por plano fora desse módulo.
- [ ] `python -m src.seed_plans`, o seed de startup do `src/main.py` e `python -m src.corrigir_admin` produzem, para os mesmos planos, **exatamente os mesmos** `allowed_brokers` (Free=`["iqoption"]`, Pro=`["iqoption","deriv"]`, VIP=`["iqoption","deriv","quotex","pocketoption"]`).
- [ ] `POST /admin/v2/fix-plan-brokers` ajusta os planos do banco para os valores de `src/plans_catalog.py` e é idempotente (rodar 2x seguidas: o 2º resultado não reporta nenhuma mudança).
- [ ] `Plan.get_allowed_brokers()` tem uma única definição em `src/models/user.py`; comportamento inalterado (retorna `[]` para `allowed_brokers` nulo/inválido).
- [ ] `VALID_BROKERS` usado na validação de `admin_routes.py` vem do módulo canônico (não há mais o set literal em `admin_routes.py:240`).
- [ ] App sobe sem erro e `GET` de plano do usuário (`src/routes/user.py`) segue retornando `allowed_brokers` corretos para um usuário de cada plano.

## Impacto em performance

**Neutro.** Todas as mudanças estão em caminhos de seed/admin (startup e endpoints de administração), nenhum no hot path de disparo de ordem. Nenhuma chamada de rede/DB nova. O import do módulo é um dict em memória.

## Plano de rollback

- Reverter o commit da implementação (`git revert`). Nenhuma linha de schema/migração muda, então o revert é limpo.
- Linhas de dados: o revert **não** altera `plans.allowed_brokers` já gravado no banco. Se algum plano ficou errado por um seeder antigo antes do fix, rodar `POST /admin/v2/fix-plan-brokers` (que após esta spec ressincroniza pela fonte única) — ou, se revertido, editar via `PUT /admin/v2/plans/{id}/brokers`.
- Risco residual: rodar um `src/*.py` de seed de uma checkout antiga reintroduz a divergência. Mitigação: rollback = revert **e** não executar scripts de seed de versão anterior.

## Aprovação

- [ ] Revisado contra `docs/sdd/CONSTITUICAO.md` (§2 fonte única — objetivo direto; §4 dedup de método; §1 sem impacto de performance; §7 autorização)
- [ ] Aprovado explicitamente pelo usuário antes do início da implementação
