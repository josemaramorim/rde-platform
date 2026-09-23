# Impedimentos — RDE_5

Lista viva de problemas conhecidos que bloqueiam evolução segura do projeto (bugs de risco financeiro/multi-tenant, débito técnico que trava performance ou manutenção). Atualizar o `Status` conforme o trabalho avança. Cada impedimento resolvido deve referenciar a spec (`docs/sdd/specs/NNN-*.md`) que o resolveu.

Status possíveis: `Aberto` · `Em análise` · `Spec aprovada` · `Resolvido`.

---

## P0 — Risco financeiro / multi-tenant

### IMP-001 — PID/log do copier compartilhados globalmente
- **Onde:** `src/main.py` (`copier.pid`, `copier.log`, rotas `/copier/toggle` e `/telegram/start-copier`)
- **Problema:** o arquivo de PID e o log do processo do Telegram copier não são namespaced por usuário. Iniciar o copier de um usuário pode matar a sessão de outro usuário que já estava operando.
- **Bloqueia:** rodar mais de um usuário com copier ativo ao mesmo tempo com segurança.
- **Status:** Resolvido — spec `docs/sdd/specs/002-copier-pid-log-por-usuario.md` (PR #6, 2026-09-11). PID e log passaram a ser `copier_{user_id}.pid`/`.log`; também fechou um vazamento de log entre usuários (`/copier/logs`) não registrado originalmente aqui, e removeu `/telegram/start-copier`/`/telegram/stop-copier` (mortos, mesmo bug).

### IMP-002 — `get_balance()` bloqueante no event loop compartilhado
- **Onde:** `src/broker/iqoption.py`, `src/broker/deriv.py`, `src/broker/_utils.py:run_async`, uso em `src/telegram_copier.py` (heartbeat 30s) e `src/routes/tradingview_bridge.py` (cache de broker)
- **Problema:** IQ Option e Deriv não têm `async_get_balance` real; a chamada síncrona bloqueia o event loop. Em `tradingview_bridge.py` isso afeta todos os usuários que compartilham o processo, não só o dono da chamada.
- **Bloqueia:** latência previsível sob carga com múltiplos usuários no webhook do TradingView.
- **Status:** Resolvido — spec `docs/sdd/specs/004-async-balance-hotpath.md` (PR #12, 2026-09-11). IQ Option e Deriv ganharam `async_get_balance` real; `_get_cached_broker` virou async; escopo também cobriu `_create_broker()` (DB síncrono + `connect()` de rede), achado durante a exploração que não estava no texto original deste impedimento.

### IMP-003 — Fallback silencioso para `R_100` na Deriv
- **Onde:** `src/broker/deriv_symbols.py`
- **Problema:** um símbolo de sinal não reconhecido é silenciosamente convertido para o índice sintético `R_100`, um ativo sem relação com o sinal original — ordem real pode ser executada no ativo errado.
- **Bloqueia:** confiança de que "o que foi sinalizado é o que foi operado" para sinais Deriv.
- **Status:** Resolvido — spec `docs/sdd/specs/003-deriv-symbol-descarte.md` (PR #9, 2026-09-11). `resolve_deriv_symbol` retorna `None` sem match confiável (removidos fallback por prefixo e default `R_100`); `telegram_copier.py` e `tradingview_bridge.py` descartam o sinal em vez de executar em ativo diferente, mesmo princípio já adotado pela IQ Option.

### IMP-004 — Regras de plano→corretora duplicadas e divergentes
- **Onde:** `src/seed_plans.py`, `src/routes/admin_routes.py` (`_PLAN_BROKER_RULES`), `src/main.py` (seed de startup), `src/corrigir_admin.py`
- **Problema:** a mesma regra de negócio (quais corretoras cada plano libera) está hardcoded em 4 lugares, e `corrigir_admin.py` diverge dos outros três. Causa raiz do endpoint manual `/admin/v2/fix-plan-brokers`.
- **Bloqueia:** confiança de que a regra de plano aplicada em produção é a intencional, sem depender de qual script rodou por último.
- **Status:** Resolvido — spec `docs/sdd/specs/001-plan-brokers-fonte-unica.md` (PR #3, 2026-09-11). Fonte única em `src/plans_catalog.py`; `/admin/v2/fix-plan-brokers` agora ressincroniza a partir dela e é idempotente.

### IMP-005 — P&L calculado com payout fixo de 85%
- **Onde:** `src/telegram_copier.py`, `src/executor.py` (uso de `stake * 0.85` em vez do `payout` real devolvido pela corretora)
- **Problema:** o valor de lucro exibido/registrado diverge do que a corretora realmente pagou, mesmo quando o payout real já está disponível na resposta da ordem (IQ Option).
- **Bloqueia:** confiabilidade dos números de P&L mostrados ao usuário e usados nas regras de ciclo/risco.
- **Status:** Resolvido — spec `docs/sdd/specs/006-resultado-e-payout-reais.md` (PR #18, 2026-09-11). Escopo real era maior: `tradingview_bridge.py::_do_wait_and_resolve` tinha um bug de tipo que fazia todo trade Deriv via TradingView ser registrado como LOSS, ganhando ou perdendo de verdade (não estava documentado aqui originalmente). Payout agora é calculado pela variação real de saldo em todos os 3 fluxos, sem percentual fixo.

### IMP-006 — Ausência de testes automatizados e de gate de CI
- **Onde:** repositório inteiro; `.github/workflows/docker-publish.yml` só builda e publica a imagem
- **Problema:** não há suíte de testes real (`src/test_trade.py` é um script manual) nem lint/type-check/test no CI. Um erro de sintaxe já chegou a ser commitado direto na `main` (commit `9aedadb`).
- **Bloqueia:** qualquer refatoração ou correção dos demais impedimentos com confiança de não quebrar produção.
- **Status:** Em análise — primeira fatia implementada: spec `docs/sdd/specs/007-testes-e-ci-inicial.md` (PR #21, 2026-09-11) adicionou `pytest`/`pytest-asyncio`, 22 testes cobrindo o que as specs 001/003/006 validaram manualmente, e o primeiro gate de CI em Pull Request do projeto (`.github/workflows/ci.yml` — sintaxe + testes). Continua **aberto**: não cobre `src/` inteiro (testes de PID/log do copier, lint/type-check e o restante do código seguem sem cobertura) — próxima fatia fica pra quando o usuário priorizar.

---

## P1 — Performance

### IMP-007 — Caches de conexão de broker duplicados e não sincronizados
- **Onde:** `src/routes/tradingview_bridge.py` (`_broker_cache`), `src/routes/broker.py` (`_broker_refresh_cache`), `src/executor.py` (`_session_cache`)
- **Problema:** eram na verdade 4 caches independentes (não 3), em 2 pares. Conexão de broker (`tradingview_bridge._broker_cache`, `routes/broker.py._broker_refresh_cache`) — desperdício de conexões, sem invalidação compartilhada. `SessionManager`/ciclo de risco (`tradingview_bridge._session_cache`, `executor._session_cache`) — mais grave: um usuário disparando sinal pelo TradingView e pelo endpoint manual `POST /signal` tinha 2 `SessionManager` independentes, podendo efetivamente dobrar o limite de risco diário.
- **Status:** Em análise — spec `docs/sdd/specs/009-session-cache-unificado.md` (PR #27, 2026-09-15) já resolveu a metade de maior risco: o par de cache de `SessionManager`, unificado em `src/services/management_3pct.py::get_session_manager`. **Ainda aberto** o par de cache de conexão de broker (`_broker_cache`/`_broker_refresh_cache`) — mais complexo de unificar (padrões de criação/async diferentes entre os arquivos), risco menor (só desperdício de reconexão, não bypass de limite financeiro). Reclassificar como `Resolvido` quando esse segundo par também for unificado.

### IMP-008 — Staleness de até 120s no status de abertura de ativo
- **Onde:** `src/broker/iqoption.py` (`_start_background_refresh`)
- **Problema:** troca deliberada de latência por staleness (bom para o disparo, mas um ativo recém-fechado pode ainda ser tentado, e um recém-aberto pode ser perdido por até 2 minutos). Vale documentar como trade-off aceito ou reduzir o intervalo.
- **Status:** Em análise (trade-off pode já ser aceitável — decisão do usuário)

### IMP-009 — Timeout fixo de 62s hardcoded na Deriv
- **Onde:** `src/broker/deriv.py` (`get_contract_status`)
- **Problema:** espera fixa de 62s antes de checar o contrato, independente do timeframe real do sinal.
- **Status:** Resolvido — spec `docs/sdd/specs/008-deriv-timeout-real.md` (PR #24, 2026-09-15). Escopo real era maior: o sleep de 62s estourava o orçamento de 90s do loop de polling em `executor.py`, fazendo todo trade Deriv ali ser registrado como LOSS por timeout (mesma classe de sintoma do IMP-005, não documentado aqui originalmente). Sleep removido; `executor.py` passou a esperar a duração fixa do contrato e decidir por variação real de saldo, mesmo método da spec 006.

---

## P2 — Débito técnico / arquitetura

### IMP-010 — `src/main.py` como "god file" (1875 linhas)
- **Onde:** `src/main.py`
- **Problema:** mistura rotas, migração SQL ad-hoc, seed de dados e um conjunto de endpoints de admin legados que duplicam (com regras diferentes) o que já existe em `admin_routes.py`.
- **Status:** Aberto

### IMP-011 — Código morto significativo
- **Onde:** `src/app/*` (scaffold paralelo nunca importado), `src/broker/connection_manager.py`, endpoints admin legados em `main.py` (`/admin/change-plan`, `/admin/liberar-cliente` com plano "Basic" inexistente, `/admin/bloquear-cliente`)
- **Problema:** código não usado por nenhum caminho real de execução, risco de confundir quem for editar e de alguém reconectar a peça errada.
- **Status:** Aberto

### IMP-012 — Binários versionados no git (`cliente/`)
- **Onde:** `cliente/` (~1287 arquivos, ~94MB — `rde-server.exe`, `cloudflared.exe`, DLLs)
- **Problema:** build empacotado do cliente versionado como código-fonte em vez de artefato de release.
- **Status:** Aberto

### IMP-013 — Segredos com fallback hardcoded
- **Onde:** `docker-compose.yml`, `docker-compose.icp.yml` (token do Telegram e chat ID como fallback), `src/core/config.py` (`ADMIN_PASSWORD` padrão `admin123456`; `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` — resolvido, spec 017), `src/telegram_copier.py` e `src/routes/telegram_auth.py` (duplicavam o fallback de `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` — resolvido, spec 017), `docs/GUIA_POSTGRESQL_E_ADMIN.md` (credenciais padrão do Postgres documentadas em texto puro)
- **Problema:** segredos reais expostos no histórico do git como valores padrão.
- **Status:** Aberto (`TELEGRAM_API_ID`/`TELEGRAM_API_HASH` resolvidos via spec 017; `ADMIN_PASSWORD`, `docker-compose*.yml` e o guia continuam pendentes — spec 010 ficou só no rascunho, código nunca foi implementado)

### IMP-014 — Três fluxos de execução de sinal parcialmente duplicados
- **Onde:** `src/telegram_copier.py`, `src/routes/tradingview_bridge.py`, `src/executor.py` + `src/celery_worker.py`
- **Problema:** lógica de negócio de execução de trade (sessão, status ao vivo, resolução de contrato) reimplementada de forma independente em três lugares.
- **Status:** Aberto

### IMP-015 — Quotex e Pocket Option provavelmente não funcionam em produção
- **Onde:** `requirements.txt`, `Dockerfile`, `src/broker/quotex.py` (`from quotexpy import ...`), `src/broker/pocketoption.py` (`from pocketoptionapi_async import ...`)
- **Problema:** as libs `quotexpy` e `pocketoptionapi-async` (usadas pelos adapters de Quotex e Pocket Option) não estão listadas em `requirements.txt` nem instaladas no `Dockerfile` — só o `iqoptionapi` está. Os imports são `try/except ImportError` com fallback silencioso pra `None` (`QuotexClient = None`, `AsyncPocketOptionClient = None`), então qualquer usuário VIP que tente usar uma dessas duas corretoras provavelmente falha ao conectar, sem essa ausência aparecer como erro óbvio de build/deploy.
- **Bloqueia:** confiança de que Quotex e Pocket Option (parte do plano VIP, ver `src/plans_catalog.py`) realmente funcionam para quem paga por elas.
- **Status:** Aberto — achado durante a exploração do IMP-002/vendorização de libs (2026-09-11), ainda não confirmado em produção nem priorizado.
