# 007 — Primeira fatia de testes automatizados + gate de CI em PRs

- **Status:** Em revisão
- **Autor:** josemaramorim (via Claude)
- **Data:** 2026-09-11
- **Impedimento(s) relacionado(s):** IMP-006 (`docs/sdd/IMPEDIMENTOS.md`). Não resolve o impedimento inteiro — é uma primeira fatia deliberadamente limitada (ver Contexto).
- **Zona de alto risco?** **Não diretamente** — não edita `src/broker/*`, `telegram_copier.py`, `tradingview_bridge.py` nem `executor.py` (só adiciona testes que os exercitam com brokers falsos, e um workflow de CI). Ainda assim segue Constituição §7 (autorização para qualquer mudança em `src/`/`frontend/` — aqui só `tests/`, `pytest.ini`, `requirements.txt` e `.github/workflows/`).

## Problema

`docs/sdd/IMPEDIMENTOS.md` registra IMP-006: zero testes automatizados reais (`src/test_trade.py` é um script manual que opera numa conta de verdade) e nenhum gate de CI além de build+publish de imagem Docker — que só roda em push pra `main`, nunca em PR. Um erro de sintaxe já chegou a ser commitado direto na `main` no passado (commit `9aedadb`).

Nos últimos 3 ciclos (specs 001, 003, 006) toda validação foi manual — escrevi casos de teste ad-hoc no terminal, confirmei que passavam, e descartei. Esse trabalho não fica protegido: se alguém reverter ou editar de novo `plans_catalog.py`, `resolve_deriv_symbol` ou o cálculo de payout, nada detecta a regressão automaticamente.

## Contexto

IMP-006 como está escrito ("ausência de testes... repositório inteiro") é grande demais pra virar uma spec só — "escrever a suíte completa" não tem um critério de pronto claro. Esta spec propõe deliberadamente uma **primeira fatia limitada**: transformar em testes de verdade exatamente os casos que já validei manualmente nas specs 001/003/006, mais um gate de CI que rode em Pull Request (algo que **nunca existiu neste projeto** — hoje CI só roda em push pra `main`, depois que o código já está lá).

Não cobre nesta fatia (fica pra uma spec futura, se o usuário quiser continuar):
- Testes end-to-end contra corretoras reais (fora de escopo pra qualquer automação — usa dinheiro real).
- Namespace de PID/log do copier (IMP-001) — testável, mas exige simular I/O de arquivo mais elaborado; deixado pra próxima fatia.
- Qualquer coisa em `frontend/`.
- Lint/type-check (`ruff`/`mypy`) — só sintaxe (`compileall`) e os testes funcionais nesta fatia.

## Proposta

### 1. Dependências de teste (`requirements.txt`)
Adiciona `pytest` e `pytest-asyncio` (o `telegram_copier.py::execute_trade` é `async def`). Mesma decisão do projeto de manter um único `requirements.txt` (sem separar dev/prod) — aceito o pequeno acréscimo no tamanho da imagem Docker em troca de simplicidade; separar em `requirements-dev.txt` fica como melhoria possível numa fatia futura, não decidida aqui.

### 2. `pytest.ini` (novo, raiz do repo)
Configura `pythonpath = .` (pra `import src.xxx` funcionar sem depender de `PYTHONPATH` externo) e `asyncio_mode = auto` (testes `async def` rodam sem precisar de `@pytest.mark.asyncio` em cada um).

### 3. `tests/` (novo diretório)
- `tests/test_plans_catalog.py` — regra canônica de plano→corretora (Free/Pro/VIP), case-insensitive, plano desconhecido retorna `[]`, formato de `plan_seed_kwargs` (spec 001).
- `tests/test_deriv_symbols.py` — match exato, match sem `-OTC`, passthrough de símbolo Deriv válido, símbolo desconhecido retorna `None`, e o caso que antes caía no fallback por prefixo (spec 003).
- `tests/test_tradingview_bridge_resolve.py` — `_do_wait_and_resolve` com broker falso: Deriv WIN/LOSS real via saldo (o bug de tipo corrigido), Quotex/Pocket Option WIN (antes sem tratamento) (spec 006).
- `tests/test_telegram_copier_payout.py` — `TelegramCopier.execute_trade` com broker/`SessionManager` reais + broker falso: WIN com payout real, e o fallback seguro quando o saldo não reflete o ganho (spec 006).
- `tests/test_executor_payout.py` — `execute_trade` do `executor.py` com o mesmo método (spec 006).

Todos os testes usam brokers falsos (nenhuma chamada de rede real, nenhum dado de produção tocado).

### 4. `.github/workflows/ci.yml` (novo)
Dispara em `pull_request` (**novo** — não existia nenhum check de PR) e em `push` pra `main`/`develop`. Passos: checkout, Python 3.13, `pip install -r requirements.txt` (o mesmo `vendor/iqoptionapi` da spec 005 já resolve local), `python -m compileall -q src` (gate de sintaxe — teria pego o commit `9aedadb`), `pytest tests/ -v`.

Não mexe em `.github/workflows/docker-publish.yml` (continua só em push pra `main`, sem gate).

### Arquivos tocados
- `requirements.txt`
- `pytest.ini` (novo)
- `tests/*.py` (novo, 5 arquivos)
- `.github/workflows/ci.yml` (novo)

Sem migração de schema. Sem edição em `src/broker/*`, `telegram_copier.py`, `tradingview_bridge.py`, `executor.py` (os testes importam e exercitam esse código, não o alteram).

## Critérios de aceite

- [ ] `pytest tests/ -v` roda localmente e todos os testes passam.
- [ ] Os testes de `resolve_deriv_symbol` e `plans_catalog` cobrem os casos documentados nas specs 001/003 (regra canônica, caso de descarte).
- [ ] Os testes de payout cobrem WIN real, LOSS real, e o fallback seguro — pros 3 fluxos (`tradingview_bridge.py`, `telegram_copier.py`, `executor.py`).
- [ ] `.github/workflows/ci.yml` dispara num Pull R real (verificável abrindo o PR desta implementação e observando o check rodar).
- [ ] `python -m compileall -q src` roda sem erro (gate de sintaxe).
- [ ] Nenhum teste faz chamada de rede real ou toca conta de corretora de verdade.

## Impacto em performance

Nenhum — testes e CI não tocam o runtime de produção nem o hot path de disparo de ordem. CI adiciona alguns segundos/minutos ao tempo de PR (não ao deploy).

## Plano de rollback

`git revert`. Sem migração de schema, sem mudança de comportamento em produção — só remove os testes e o workflow de CI.

## Aprovação

- [ ] Revisado contra `docs/sdd/CONSTITUICAO.md` (§7 autorização; sem violação de §1/§2/§3/§4/§5/§6)
- [ ] Aprovado explicitamente pelo usuário antes do início da implementação
