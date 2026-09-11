# 006 — Resultado e payout reais (calculados pela variação de saldo)

- **Status:** Em revisão
- **Autor:** josemaramorim (via Claude)
- **Data:** 2026-09-11
- **Impedimento(s) relacionado(s):** IMP-005 (`docs/sdd/IMPEDIMENTOS.md`). Escopo apurado é mais grave que o texto original — inclui um bug de tipo que faz a Deriv (e a ausência total de tratamento para Quotex/Pocket Option) resolverem **todo trade via TradingView como LOSS**, não só o valor do payout.
- **Zona de alto risco?** **Sim** — toca `src/telegram_copier.py`, `src/routes/tradingview_bridge.py` e `src/executor.py`, os três nomeados explicitamente na zona de alto risco do `CLAUDE.md`.

## Problema

O valor de lucro de uma operação vencedora é hardcoded como `stake * 0.85` em três lugares (`src/telegram_copier.py:1111`, `src/executor.py:219`, `src/routes/tradingview_bridge.py:759` no branch Deriv) — um payout fixo de 85%, mesmo quando o valor real pago pela corretora é diferente (e, no caso da IQ Option, já está disponível na resposta da ordem).

Só que a exploração revelou algo mais grave que "número de lucro impreciso": em `src/routes/tradingview_bridge.py::_do_wait_and_resolve` (o resolvedor de resultado do webhook TradingView, roda em thread separada), o branch da Deriv tem um **bug de tipo**:

```python
status = broker.get_contract_status(contract_id)   # Deriv retorna uma STRING: "won"/"lost"/"error"
balance_after = broker.get_balance()
if status and status.get("result") == "won":         # .get() numa string -> AttributeError
    profit = stake * 0.85
elif status and status.get("result") == "lost":
    profit = -stake
```

`DerivBroker.get_contract_status` (`src/broker/deriv.py:244`) retorna uma **string**, não um dict. `.get("result")` numa string lança `AttributeError`, capturado pelo `except Exception as e: logger.warning(...)` logo abaixo — e o código segue com `profit` no valor inicializado antes do bloco (`profit = -stake`, linha 722). **Resultado: toda operação de Deriv executada via TradingView é registrada como LOSS, independente do resultado real** — não é só o payout que está errado, é o resultado inteiro (WIN vira LOSS no dashboard, no `session_manager`/ciclo de risco, e no registro de auditoria).

Quotex e Pocket Option **nem têm um branch** em `_do_wait_and_resolve` — caem direto no mesmo `profit = -stake` padrão. Hoje isso é menos urgente na prática (IMP-015: essas corretoras provavelmente nem conectam), mas o bug já existe pronto pra morder assim que o IMP-015 for corrigido.

Resumo por corretora e por fluxo de execução (são 3 fluxos parcialmente duplicados — IMP-014):

| Corretora | Via Telegram (`telegram_copier.py`) | Via TradingView (`tradingview_bridge.py`) |
|---|---|---|
| IQ Option | Payout fixo 85% | **Já correto** — calcula profit pela variação real de saldo |
| Deriv | Payout fixo 85% | **Bug de tipo — sempre LOSS** |
| Quotex | Payout fixo 85% (código genérico) | Sem tratamento — sempre LOSS |
| Pocket Option | Payout fixo 85% (código genérico) | Sem tratamento — sempre LOSS |

(`src/executor.py` roda um quarto caminho, sem diferenciar corretora — o mesmo `stake * 0.85` genérico, linha 219.)

## Contexto

`src/routes/tradingview_bridge.py` já resolve isso **corretamente** para IQ Option: em vez de confiar num payout fixo ou parsear a resposta específica da corretora, ele compara o saldo antes e depois do trade (`profit = balance_after - session_manager.current_balance`). Esse método é broker-agnóstico — funciona pra qualquer corretora que exponha `get_balance()`/`async_get_balance()` (todas as 4, desde o IMP-002) — e reflete exatamente o que a corretora pagou de verdade, sem precisar confiar no formato de resposta de cada uma.

`self._balance_before_trade` (`telegram_copier.py:1043`) e a variável `balance` (`executor.py`, capturada antes do `send_order`) já guardam o saldo anterior ao trade nos outros dois fluxos — só não são usados pra calcular o profit real, que seguem usando o valor fixo.

## Proposta

Generalizar o método "saldo antes vs. saldo depois" (já correto pra IQ Option em `tradingview_bridge.py`) pros outros pontos, em vez de inventar um tratamento por corretora:

### 1. `src/routes/tradingview_bridge.py::_do_wait_and_resolve`
- Remove o branch quebrado da Deriv (bug de tipo).
- Unifica Deriv + Quotex + Pocket Option (+ qualquer broker futuro) num único `else` genérico: `balance_after = broker.get_balance()`, `profit = balance_after - (session_manager.current_balance or session_manager.initial_balance)`, mesmo padrão de log já usado no branch IQ Option. Sem parsing de contrato, sem payout hardcoded.
- Branch da IQ Option **não muda** — já está correto, usa uma consulta de saldo mais precisa (`broker.api.get_balances()` filtrando pelo `backendapi_balance_id`); não vale o risco de trocar por algo genérico.

### 2. `src/telegram_copier.py`
Na função que processa o resultado (linha ~1109-1114): quando `trade_status == "won"`, troca `profit = stake * 0.85` por `profit = self.current_balance - self._balance_before_trade` (ambos já disponíveis nesse ponto). Se o delta vier `<= 0` (saldo pode não ter atualizado ainda no broker), espera mais 3s e busca o saldo de novo uma vez; se ainda assim vier `<= 0`, registra `profit = 0.0` com log de aviso — nunca inventa um payout, só não deixa negativo/zerado silencioso sem explicação.

### 3. `src/executor.py`
Mesmo ajuste no branch BINARY (linha ~208-219): busca `balance_after = broker.get_balance()` depois de confirmar `trade_status`, calcula `profit_delta = balance_after - balance` para WIN, com a mesma salvaguarda de retry/log do item 2.

### Arquivos tocados
- `src/routes/tradingview_bridge.py` (zona de alto risco)
- `src/telegram_copier.py` (zona de alto risco)
- `src/executor.py` (zona de alto risco)

Sem migração de schema. `src/broker/*.py` não muda — usa só a interface `get_balance()`/`async_get_balance()` que já existe (IMP-002).

## Critérios de aceite

- [ ] `grep -rn "stake \* 0\.85\|stake\*0\.85"` não encontra mais nenhuma ocorrência em `src/`.
- [ ] Simulação com broker falso (Deriv): saldo sobe após a espera → `_do_wait_and_resolve` registra `profit > 0` correspondente à alta real, não mais sempre `-stake`.
- [ ] Simulação com broker falso "quotex"/"pocketoption" (sem branch específico): mesma coisa — cai no `else` genérico e calcula o profit real, não mais sempre `-stake`.
- [ ] `telegram_copier.py`: com `trade_status == "won"` e saldo simulando alta real, `profit` bate com a diferença de saldo, não com `stake * 0.85`.
- [ ] `executor.py`: mesmo teste no branch BINARY.
- [ ] Caso saldo não reflita o ganho mesmo depois do retry: `profit` vira `0.0` com log de aviso — nunca um valor negativo pra um WIN confirmado, nem um payout inventado.
- [ ] Comportamento da IQ Option em `tradingview_bridge.py` inalterado (mesma lógica de antes, não tocada).
- [ ] Import de todos os módulos tocados limpo; app sobe sem erro.

## Impacto em performance

Neutro — todas as chamadas de `get_balance()`/`async_get_balance()` já existiam nesses pontos (ou substituem uma chamada de rede equivalente, `get_contract_status`, que também já existia). Nenhum I/O novo introduzido; o retry de 3s no telegram_copier.py/executor.py só acontece no caso raro de saldo ainda não refletido (não é hot path de disparo, é resolução de resultado após a expiração do contrato).

## Plano de rollback

`git revert`. Sem migração de schema, sem dado persistido alterado por este fix (o efeito é só no cálculo de `profit`/`profit_delta` registrado dali em diante).

## Aprovação

- [ ] Revisado contra `docs/sdd/CONSTITUICAO.md` (§1 sem impacto de performance; §2 fonte única — unifica em vez de duplicar tratamento por corretora; §3 zona de alto risco — autorização explícita obrigatória; §7 autorização)
- [ ] Aprovado explicitamente pelo usuário antes do início da implementação
