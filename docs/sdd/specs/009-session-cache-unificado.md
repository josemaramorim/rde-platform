# 009 — Fonte única para o cache de SessionManager (ciclo de risco)

- **Status:** Implementado (PR #27, mergeado em 2026-09-15)
- **Autor:** josemaramorim (via Claude)
- **Data:** 2026-09-15
- **Impedimento(s) relacionado(s):** IMP-007 (`docs/sdd/IMPEDIMENTOS.md`). Escopo desta spec cobre só a metade mais arriscada do impedimento (ver Contexto) — a duplicação de cache de *conexão* de broker fica para uma spec futura.
- **Zona de alto risco?** **Parcial** — `src/executor.py` está explicitamente na zona de alto risco do `CLAUDE.md`; `src/routes/tradingview_bridge.py` idem. `src/services/management_3pct.py` (onde a fonte única passa a viver) não está na lista, mas é consultado com o mesmo cuidado por guardar a lógica de ciclo de risco. Exige autorização explícita (Constituição §3/§7).

## Problema

IMP-007 documenta "3 caches independentes de conexão/estado de broker" em `tradingview_bridge.py`, `routes/broker.py` e `executor.py`. A exploração encontrou que são na verdade **4 caches independentes**, agrupados em 2 pares com propósitos diferentes:

1. **Caches de conexão de broker** (menor risco — só desperdício de reconexão): `tradingview_bridge._broker_cache` e `routes/broker.py._broker_refresh_cache`.
2. **Caches de `SessionManager`** (risco real de negócio): `tradingview_bridge._session_cache` e `executor._session_cache` — **código duplicado quase idêntico** (mesma função `_get_session_manager`, copiada entre os dois arquivos).

Esta spec cobre só o item 2. `SessionManager` é o objeto que rastreia o **ciclo de risco diário** de um usuário (3 sessões de 1%, meta de 3% ao dia, martingale de recuperação). Como cada arquivo mantém seu próprio dicionário em memória:

- Um usuário que dispara sinal pelo **TradingView** (`/tradingview/webhook` → `tradingview_bridge.py`) tem um `SessionManager`.
- O mesmo usuário disparando pelo endpoint manual **`POST /signal`** (`src/main.py:1145` → Celery → `src/executor.py`, **rota real e ativa**, não código morto) tem **outro** `SessionManager`, começando do zero.

Um usuário usando os dois canais no mesmo dia efetivamente **dobra o próprio limite de risco diário** — cada canal acha que está começando a sessão do zero, sem saber que o outro já operou. Isso viola a Constituição §2 (fonte única para regra de negócio) e é um risco financeiro real, não só ineficiência.

## Contexto

As duas funções `_get_session_manager` (`tradingview_bridge.py:207-227`, `executor.py:35-51`) são **funcionalmente idênticas** — mesma chave de cache (`f"{user_id}_{broker_name}"`), mesma lógica de reset diário/por-corretora, mesma estrutura de entrada no dict. Não é um caso de "duas implementações que divergem sutilmente" (como o IMP-004 antes da fonte única) — é cópia literal. Unificar é mecânico e de baixo risco de regressão comportamental por si só; o único efeito observável pretendido é que os dois fluxos passem a enxergar o **mesmo** `SessionManager` pra um dado `user_id`+`broker_name`.

`src/telegram_copier.py` **não** participa dessa duplicação — cada usuário já roda seu próprio subprocesso (IMP-001), então `self.session_manager` já é naturalmente isolado por usuário, sem precisar de cache compartilhado em dicionário.

**Fora de escopo desta spec** (fica pra uma spec futura, se o usuário priorizar): unificar os caches de *conexão* de broker (`tradingview_bridge._broker_cache` e `routes/broker.py._broker_refresh_cache`). São mais complexos de unificar — usam padrões de criação/async diferentes entre os dois arquivos — e o risco é só desperdício de reconexão, não bypass de limite de risco.

## Proposta

### 1. `src/services/management_3pct.py`
Adiciona, no mesmo arquivo onde `SessionManager` já vive (fonte única do conceito de ciclo de risco): `_session_cache: Dict[str, dict]`, `_cache_lock: threading.Lock`, e `get_session_manager(user_id, balance, broker_name="") -> SessionManager` — a mesma lógica hoje duplicada, agora canônica e pública (sem `_` no nome, é a API compartilhada).

### 2. `src/routes/tradingview_bridge.py`
Remove `_session_cache` e `_get_session_manager` locais; importa e usa `get_session_manager` de `management_3pct.py`. `_broker_cache`/`_cache_lock` (conexão, fora de escopo) não são tocados.

### 3. `src/executor.py`
Mesma coisa: remove `_session_cache`/`_cache_lock`/`_get_session_manager` locais; importa e usa a versão canônica.

### Arquivos tocados
- `src/services/management_3pct.py`
- `src/routes/tradingview_bridge.py`
- `src/executor.py` (zona de alto risco)

Sem migração de schema. `SessionManager` em si (a classe) não muda — só onde o cache que a instancia/reaproveita vive.

## Critérios de aceite

- [x] `grep -rn "_get_session_manager\|_session_cache" src/routes/tradingview_bridge.py src/executor.py` não encontra mais definição local — só o import/uso da versão canônica.
- [x] Simulação: chamar `get_session_manager(user_id, 100.0, "deriv")` a partir de um contexto simulando `tradingview_bridge.py` e depois a partir de um contexto simulando `executor.py` (mesmo `user_id`/`broker_name`) retorna a **mesma instância** de `SessionManager` — não duas independentes.
- [x] Reset diário/por-corretora continua funcionando (mesmo comportamento de antes: SessionManager novo se mudar o dia ou a corretora).
- [x] `telegram_copier.py` inalterado (não participa deste cache).
- [x] `pytest tests/ -v` passa (testes existentes da spec 007/008, sem regressão) e novos testes cobrindo o compartilhamento entre os dois arquivos.
- [x] Import de todos os módulos tocados limpo; app sobe sem erro.

## Impacto em performance

Neutro — mesma operação de dict/lock em memória, só centralizada num lugar em vez de duplicada. Nenhuma chamada de rede/DB nova.

## Plano de rollback

`git revert`. Sem migração de schema. Nenhum dado persistido é afetado — o cache é só em memória do processo, reiniciado a cada deploy de qualquer forma.

## Aprovação

- [x] Revisado contra `docs/sdd/CONSTITUICAO.md` (§2 fonte única — objetivo direto desta spec; §3 zona de alto risco parcial; §7 autorização)
- [x] Aprovado explicitamente pelo usuário antes do início da implementação (2026-09-15)
