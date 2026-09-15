# 008 — Remove o sleep(62) fixo da Deriv; corrige polling em executor.py

- **Status:** Implementado (PR #24, mergeado em 2026-09-15)
- **Autor:** josemaramorim (via Claude)
- **Data:** 2026-09-14
- **Impedimento(s) relacionado(s):** IMP-009 (`docs/sdd/IMPEDIMENTOS.md`). Escopo apurado é mais grave que "espera imprecisa" — inclui um caso em que `executor.py` provavelmente registra todo trade Deriv como LOSS por timeout, mesma classe de sintoma do IMP-005 (já resolvido nos outros 2 fluxos), só que por timing em vez de bug de tipo.
- **Zona de alto risco?** **Sim** — toca `src/broker/deriv.py` e `src/executor.py`, ambos na zona de alto risco do `CLAUDE.md`.

## Problema

`DerivBroker._get_contract_status_async` (`src/broker/deriv.py:247-248`) tem um `await asyncio.sleep(62)` fixo, sem relação com o timeframe do sinal nem com a duração real do contrato (introduzido assim desde o commit inicial `ecb725b`, sem comentário explicando o valor).

Contratos Deriv duram sempre **3 minutos fixos** (`DerivBroker.DERIV_EXPIRATION_MINUTES = 3`, já estabelecido nas specs 003/006 — não varia por timeframe do sinal). Isso expõe dois problemas diferentes dependendo de quem chama:

1. **`src/telegram_copier.py:1091`** — já espera a duração completa antes de chamar (`await asyncio.sleep(duration*60+3)` ≈ 183s, com `duration` ajustado pra `DERIV_EXPIRATION_MINUTES`). O `sleep(62)` interno soma **mais ~62s por cima**, sem necessidade — puro desperdício de latência (o código já tem um árbitro de fallback via variação de saldo se o status vier incerto, então a correção real do resultado não depende desse sleep).

2. **`src/executor.py:208-217`** — o loop de polling genérico (usado por IQ Option, Deriv, Quotex, Pocket Option) tem um orçamento de **90 segundos** (`deadline = time.time() + 90`), fazendo `time.sleep(5)` + `broker.get_contract_status(contract_id)` a cada volta, esperando uma chamada rápida. Como a chamada da Deriv bloqueia **62s por dentro**, uma única iteração já consome 67 dos 90s de orçamento; depois de 2 iterações (~134s) o loop desiste — mas o contrato Deriv (180s de duração) ainda nem expirou. `trade_status` fica em `"error"`, e `outcome = "win" if trade_status == "won" else "loss"` resolve pra **LOSS**, ganhando ou perdendo de verdade. **Provavelmente todo trade Deriv executado via `executor.py` é registrado como LOSS**, mesma classe de sintoma do IMP-005 (já corrigido nos outros 2 fluxos — `telegram_copier.py` e `tradingview_bridge.py`), só que causado por timing incompatível em vez de um bug de tipo.

## Contexto

`get_contract_status`/`async_get_contract_status` da IQ Option, Quotex e Pocket Option **não têm sleep interno** — consultam o status imediatamente quando chamadas, e o padrão de polling em `executor.py` (checar a cada 5s, dentro de um orçamento) faz sentido pra elas. Só a Deriv tem esse comportamento diferente (bloquear a chamada por 62s), o que quebra a suposição do loop genérico.

A spec 006 já estabeleceu o método correto pra determinar resultado da Deriv nos outros 2 fluxos: esperar a duração completa do contrato, depois comparar saldo antes/depois — sem depender de `get_contract_status`. Esta spec estende o mesmo método pro `executor.py`, em vez de tentar consertar o polling genérico pra acomodar o caso especial da Deriv.

## Proposta

### 1. `src/broker/deriv.py`
Remove o `await asyncio.sleep(62)` de `_get_contract_status_async` — a função passa a consultar o status imediatamente, como já fazem os métodos equivalentes das outras 3 corretoras. Quem chama é responsável por já ter esperado a duração apropriada (verdade hoje em `telegram_copier.py`).

### 2. `src/executor.py`
No branch BINARY, separa o caso Deriv do loop de polling genérico: em vez de tentar `get_contract_status` num orçamento de 90s (insuficiente pros 180s fixos da Deriv), espera a duração completa (`DerivBroker.DERIV_EXPIRATION_MINUTES * 60 + 5`) e decide WIN/LOSS pela variação real de saldo — mesmo método já usado em `telegram_copier.py` e `tradingview_bridge.py` (spec 006). IQ Option, Quotex e Pocket Option continuam no loop de polling genérico, inalterado.

### Arquivos tocados
- `src/broker/deriv.py` (zona de alto risco)
- `src/executor.py` (zona de alto risco)

Sem migração de schema. `telegram_copier.py` e `tradingview_bridge.py` não precisam de edição — já esperam a duração certa e/ou já usam variação de saldo (specs 003/006).

## Critérios de aceite

- [x] `grep -n "asyncio.sleep(62)" src/broker/deriv.py` não encontra mais nada.
- [x] Simulação: `_get_contract_status_async` chamada diretamente (sem esperar) retorna o status da primeira consulta, sem atraso interno.
- [x] `executor.py`: trade Deriv simulado com saldo subindo (WIN real) e um `get_contract_status` falso que nunca resolveria a tempo no loop antigo — registra `outcome="win"` e `profit_delta` correto, não mais `"loss"` por timeout.
- [x] `executor.py`: trade Deriv simulado com saldo caindo (LOSS real) continua registrando `outcome="loss"` corretamente.
- [x] IQ Option, Quotex e Pocket Option em `executor.py` continuam usando o loop de polling genérico, comportamento inalterado.
- [x] `telegram_copier.py`: fluxo continua funcionando (usa o árbitro de saldo já existente se `get_contract_status` vier incerto) — sem regressão, testável reexecutando os testes da spec 006/007 que já cobrem esse arquivo.
- [x] Testes novos adicionados em `tests/` (spec 007 já deixou a infraestrutura de teste pronta) e `pytest tests/ -v` passa, incluindo os testes já existentes.
- [x] Import de todos os módulos tocados limpo; app sobe sem erro.

## Impacto em performance

**Melhora a latência** no fluxo do Telegram (remove ~62s de espera redundante por trade Deriv) e **corrige a confiabilidade do resultado** no `executor.py` (elimina o timeout prematuro que fazia trades Deriv sempre virarem LOSS). Nenhuma chamada de rede nova introduzida.

## Plano de rollback

`git revert`. Sem migração de schema, sem dado persistido alterado além do cálculo de `outcome`/`profit_delta` dali em diante.

## Aprovação

- [x] Revisado contra `docs/sdd/CONSTITUICAO.md` (§1 melhora de latência — objetivo direto; §3 zona de alto risco — autorização explícita obrigatória; §7 autorização)
- [x] Aprovado explicitamente pelo usuário antes do início da implementação (2026-09-15)
