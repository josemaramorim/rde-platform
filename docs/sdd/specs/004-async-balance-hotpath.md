# 004 — Offload de I/O bloqueante no hot path do webhook TradingView

- **Status:** Implementado (PR #12, mergeado em 2026-09-11)
- **Autor:** josemaramorim (via Claude)
- **Data:** 2026-09-11
- **Impedimento(s) relacionado(s):** IMP-002 (`docs/sdd/IMPEDIMENTOS.md`). Escopo apurado inclui mais do que `get_balance()` (ver Contexto).
- **Zona de alto risco?** **Sim** — toca `src/broker/iqoption.py`, `src/broker/deriv.py` e `src/routes/tradingview_bridge.py` (webhook do TradingView, processo compartilhado entre usuários). Exige autorização explícita antes da implementação (Constituição §3).

## Problema

`GET /tradingview/webhook` roda no processo FastAPI **compartilhado entre todos os usuários**. O handler (`receive_tradingview_webhook` → `_execute_tv_trade`, ambos `async def`) chama `_get_cached_broker()` **sem `await`, sem offload** — uma função síncrona que, no caminho mais comum (cache expirado ou health-check falhou), executa I/O de rede bloqueante direto na thread do event loop:

1. **`broker.get_balance()`** (`src/routes/tradingview_bridge.py:55`, o health-check do broker em cache) — para IQ Option e Deriv não existe `async_get_balance` real (IMPEDIMENTOS.md já documentava isso).
2. **`_create_broker()`** (`src/routes/tradingview_bridge.py:76`, chamado em cache-miss/expirado, e de novo nas 2 rotas de reconexão em `_execute_tv_trade`, linhas ~558 e ~579) — faz uma query síncrona no banco (`SessionLocal()`, não a sessão async) **e** `broker.connect()` (login/handshake de rede, potencialmente vários segundos para IQ Option). Isso não estava no texto original do IMP-002, mas é o mesmo bug na mesma função — corrigir só o `get_balance()` e deixar `_create_broker()` bloqueando teria um efeito prático pequeno, já que a conexão inicial costuma ser mais lenta que o health-check.

Enquanto qualquer uma dessas chamadas está em andamento, **todo o processo fica bloqueado** — nenhum outro usuário consegue disparar ordem, nem checar status, nem nada que passe por esse processo, pelo tempo que a chamada de rede levar. Isso viola diretamente a Constituição §1 ("nenhuma chamada de rede ou DB bloqueante dentro de código async sem offload explícito... vale em especial para tradingview_bridge.py") e ataca o requisito não-funcional #1 do projeto (latência de disparo de ordem) exatamente no pior lugar possível: o webhook compartilhado.

`src/telegram_copier.py` também é citado no IMP-002 original (`_refresh_balance`, heartbeat 30s, linha ~928-937): já prefere `async_get_balance` quando existe, mas cai para uma chamada síncrona direta quando não existe. Como cada usuário roda seu próprio subprocesso do copier (IMP-001, já resolvido), esse bloqueio fica contido a UM usuário — ainda assim vale corrigir pra não atrasar o processamento de sinais desse usuário durante o refresh.

## Contexto

Deriv **já tem** uma implementação assíncrona real e nativa (`_get_balance_async`, `src/broker/deriv.py:229-233`, via WebSocket) — só não está exposta publicamente como `async_get_balance`; o wrapper síncrono `get_balance()` usa `run_async()` (`src/broker/_utils.py`), que roda a coroutine numa thread separada e **espera bloqueando** (`future.result(timeout=120)`) — ou seja, mesmo o Deriv, que tem async de verdade por baixo, acaba sendo consumido de forma bloqueante.

IQ Option não tem nenhum caminho assíncrono nativo (a lib `iqoptionapi` por baixo é síncrona) — o único jeito de ter um `async_get_balance` real ali é fazer offload explícito pra thread (`asyncio.to_thread`), exatamente como a Constituição §1 pede ("expor uma versão async_* real — não um wrapper que bloqueia a thread via run_async").

Quotex e Pocket Option **já têm** `async_get_balance` real (`src/broker/quotex.py:243-248`, `src/broker/pocketoption.py:218+`) — não são afetados por esta spec, servem de modelo de estilo pro que se propõe aqui.

**Fora de escopo:** `broker.disconnect()` (chamado em vários pontos do mesmo arquivo) continua síncrono — é fire-and-forget, sempre dentro de `try/except`, menor risco de travar por muito tempo. `src/executor.py` e o IMP-007 (caches de broker duplicados) não são tocados aqui.

## Proposta

### 1. `src/broker/iqoption.py`
Adiciona `async def async_get_balance(self) -> float:` que roda o corpo atual de `get_balance()` via `asyncio.to_thread` — não é um wrapper que bloqueia a thread chamadora, é offload real.

### 2. `src/broker/deriv.py`
Adiciona `async def async_get_balance(self) -> float:` — wrapper fino: `return await self._get_balance_async()`, reaproveitando a implementação nativa já existente. `get_balance()` (síncrono, via `run_async`) continua existindo para quem ainda chama de fora de contexto async (ex.: scripts).

### 3. `src/routes/tradingview_bridge.py`
- `_get_cached_broker` passa a ser `async def`:
  - Health-check: `await broker.async_get_balance()` (todo broker relevante passa a ter esse método após os passos 1-2; mantém fallback defensivo `await asyncio.to_thread(broker.get_balance)` para qualquer adapter futuro sem `async_get_balance`).
  - Criação/reconexão: `_create_broker(...)` passa a ser chamado como `await asyncio.to_thread(_create_broker, user_id, broker_name)` nos 3 pontos onde aparece (dentro de `_get_cached_broker`, e nas 2 rotas de reconexão em `_execute_tv_trade`) — sem mudar a lógica interna de `_create_broker`, só tirando-a do event loop.
- Único call site (`broker = _get_cached_broker(...)`) passa a `broker = await _get_cached_broker(...)`.

### 4. `src/telegram_copier.py`
`_refresh_balance`: quando `async_get_balance` não existe no broker, troca a chamada direta `self.broker.get_balance()` por `await asyncio.to_thread(self.broker.get_balance)`.

### Arquivos tocados
- `src/broker/iqoption.py` (zona de alto risco)
- `src/broker/deriv.py` (zona de alto risco)
- `src/routes/tradingview_bridge.py` (zona de alto risco)
- `src/telegram_copier.py` (zona de alto risco)

Sem migração de schema. Quotex, Pocket Option e o restante do fluxo (parsing de sinal, sessão, gestão de risco) inalterados.

## Critérios de aceite

- [x] `IQOptionBroker` e `DerivBroker` expõem `async_get_balance()` (`hasattr(broker, "async_get_balance")` verdadeiro pros 4 brokers suportados).
- [x] Chamar `await broker.async_get_balance()` não bloqueia o event loop: uma coroutine concorrente simples (`asyncio.sleep(0)` num loop) continua sendo agendada normalmente enquanto a chamada de balance está em andamento.
- [x] `_get_cached_broker` é `async def`; o único call site em `_execute_tv_trade` usa `await`.
- [x] `_create_broker` só é invocado via `asyncio.to_thread` nos 3 pontos de `tradingview_bridge.py` — nenhuma chamada direta (síncrona) restante dentro de função `async def`.
- [x] `telegram_copier.py::_refresh_balance` não chama `self.broker.get_balance()` direto quando `async_get_balance` não existe — usa `asyncio.to_thread`.
- [x] App sobe sem erro; import de todos os módulos tocados limpo.
- [x] Comportamento observável para o usuário final inalterado (mesmo resultado de saldo/execução) — só deixa de bloquear o processo compartilhado.

## Impacto em performance

**Este é o objetivo central da spec: melhora latência sob carga concorrente**, eliminando bloqueio do event loop compartilhado no webhook do TradingView. Nenhuma chamada de rede/DB nova é introduzida — só offload explícito (`asyncio.to_thread`) do I/O que já existia, exatamente como a Constituição §1 pede.

## Plano de rollback

`git revert` — sem migração de schema, sem dado persistido alterado. Reverte para: `get_balance()`/`_create_broker()` voltam a bloquear o event loop compartilhado durante cache-miss/reconexão (comportamento atual).

## Aprovação

- [x] Revisado contra `docs/sdd/CONSTITUICAO.md` (§1 performance-first — objetivo direto desta spec; §3 zona de alto risco — autorização explícita obrigatória; §7 autorização)
- [x] Aprovado explicitamente pelo usuário antes do início da implementação (2026-09-11)
