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
- **Status:** Aberto

### IMP-006 — Ausência de testes automatizados e de gate de CI
- **Onde:** repositório inteiro; `.github/workflows/docker-publish.yml` só builda e publica a imagem
- **Problema:** não há suíte de testes real (`src/test_trade.py` é um script manual) nem lint/type-check/test no CI. Um erro de sintaxe já chegou a ser commitado direto na `main` (commit `9aedadb`).
- **Bloqueia:** qualquer refatoração ou correção dos demais impedimentos com confiança de não quebrar produção.
- **Status:** Aberto

---

## P1 — Performance

### IMP-007 — Caches de conexão de broker duplicados e não sincronizados
- **Onde:** `src/routes/tradingview_bridge.py` (`_broker_cache`), `src/routes/broker.py` (`_broker_refresh_cache`), `src/executor.py` (`_session_cache`)
- **Problema:** três caches independentes de conexão/estado de broker, sem invalidação compartilhada — desperdício de conexões e risco de estado inconsistente entre eles.
- **Status:** Aberto

### IMP-008 — Staleness de até 120s no status de abertura de ativo
- **Onde:** `src/broker/iqoption.py` (`_start_background_refresh`)
- **Problema:** troca deliberada de latência por staleness (bom para o disparo, mas um ativo recém-fechado pode ainda ser tentado, e um recém-aberto pode ser perdido por até 2 minutos). Vale documentar como trade-off aceito ou reduzir o intervalo.
- **Status:** Em análise (trade-off pode já ser aceitável — decisão do usuário)

### IMP-009 — Timeout fixo de 62s hardcoded na Deriv
- **Onde:** `src/broker/deriv.py` (`get_contract_status`)
- **Problema:** espera fixa de 62s antes de checar o contrato, independente do timeframe real do sinal.
- **Status:** Aberto

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
- **Onde:** `docker-compose.yml`, `docker-compose.icp.yml` (token do Telegram e chat ID como fallback), `src/core/config.py` (`ADMIN_PASSWORD` padrão `admin123456`), `docs/GUIA_POSTGRESQL_E_ADMIN.md` (credenciais padrão do Postgres documentadas em texto puro)
- **Problema:** segredos reais expostos no histórico do git como valores padrão.
- **Status:** Aberto

### IMP-014 — Três fluxos de execução de sinal parcialmente duplicados
- **Onde:** `src/telegram_copier.py`, `src/routes/tradingview_bridge.py`, `src/executor.py` + `src/celery_worker.py`
- **Problema:** lógica de negócio de execução de trade (sessão, status ao vivo, resolução de contrato) reimplementada de forma independente em três lugares.
- **Status:** Aberto

### IMP-015 — Quotex e Pocket Option provavelmente não funcionam em produção
- **Onde:** `requirements.txt`, `Dockerfile`, `src/broker/quotex.py` (`from quotexpy import ...`), `src/broker/pocketoption.py` (`from pocketoptionapi_async import ...`)
- **Problema:** as libs `quotexpy` e `pocketoptionapi-async` (usadas pelos adapters de Quotex e Pocket Option) não estão listadas em `requirements.txt` nem instaladas no `Dockerfile` — só o `iqoptionapi` está. Os imports são `try/except ImportError` com fallback silencioso pra `None` (`QuotexClient = None`, `AsyncPocketOptionClient = None`), então qualquer usuário VIP que tente usar uma dessas duas corretoras provavelmente falha ao conectar, sem essa ausência aparecer como erro óbvio de build/deploy.
- **Bloqueia:** confiança de que Quotex e Pocket Option (parte do plano VIP, ver `src/plans_catalog.py`) realmente funcionam para quem paga por elas.
- **Status:** Aberto — achado durante a exploração do IMP-002/vendorização de libs (2026-09-11), ainda não confirmado em produção nem priorizado.
