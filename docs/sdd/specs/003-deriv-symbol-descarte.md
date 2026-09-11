# 003 — Deriv: descartar sinal em vez de adivinhar ativo não mapeado

- **Status:** Implementado (PR #9, mergeado em 2026-09-11)
- **Autor:** josemaramorim (via Claude)
- **Data:** 2026-09-11
- **Impedimento(s) relacionado(s):** IMP-003 (`docs/sdd/IMPEDIMENTOS.md`).
- **Zona de alto risco?** **Sim** — toca `src/telegram_copier.py` e `src/routes/tradingview_bridge.py` (webhook do TradingView, processo compartilhado entre usuários). Exige autorização explícita antes da implementação (Constituição §3).

## Problema

`resolve_deriv_symbol` (`src/broker/deriv_symbols.py:55-97`) tem **duas camadas de "adivinhação silenciosa"** além do mapeamento canônico:

1. **Fallback por prefixo** (linhas 84-94): para um símbolo que não bateu no mapa exato nem no mapa sem `-OTC`, tenta `sym.startswith(prefix)` contra uma lista fixa e retorna o ativo Deriv associado a esse prefixo — um palpite, não um alias confirmado.
2. **Default final** (linhas 96-97): se nada bateu, `return "R_100"` — um índice sintético **sem nenhuma relação** com o sinal original.

Os dois pontos que chamam essa função — `src/telegram_copier.py:915` e `src/routes/tradingview_bridge.py:198` (via `_map_symbol`) — usam o valor retornado **direto**, sem checar se foi um match real ou um palpite, e mandam a ordem pra corretora. Resultado: um sinal com símbolo não reconhecido na Deriv pode acabar executando uma ordem real num ativo completamente diferente do que foi sinalizado.

Este é exatamente o mesmo tipo de bug que a IQ Option já teve e foi corrigido (commit `3ec4f25`, "remove todos fallbacks automaticos — executa exatamente o ativo do sinal ou descarta"). O padrão que resultou está em `src/broker/iqoption.py:409-411`: quando o ativo não é encontrado, loga `❌ [SINAL DESCARTADO]` e retorna erro — **sem substituição**. A Deriv nunca recebeu o mesmo tratamento na camada de resolução de símbolo.

## Contexto

Vale registrar, sem tocar agora: o próprio `DERIV_SYMBOL_MAP` (o mapeamento canônico, não o fallback) já associa pares forex/cripto reais (`EURUSD`, `XAUUSD`, `BTCUSD`...) a índices sintéticos da Deriv (`R_100`, `1HZ250V`, `cryBTCUSD`...) — instrumentos diferentes do que o sinal nomeia. Essa é uma estratégia deliberada e já curada (todo o mapa foi construído par a par), não um bug de fallback — está fora do escopo desta spec. Se fizer sentido revisitar se sinais de forex real deveriam ir pra Deriv dessa forma, é uma decisão de produto separada, não um IMP-003.

Esta spec cobre só as duas camadas de **adivinhação sem confirmação** (fallback por prefixo e default `R_100`), aplicando à Deriv o mesmo princípio já adotado pela IQ Option: executar exatamente o que o sinal pede, ou descartar.

## Proposta

### 1. `src/broker/deriv_symbols.py`
`resolve_deriv_symbol` passa a retornar `Optional[str]`:
- **Mantém** (matches confiáveis, não são fallback): match exato no `DERIV_SYMBOL_MAP`, match após remover `-OTC`, símbolo que já é um ativo Deriv válido (passthrough).
- **Remove** o bloco de "fallback inteligente por prefixo" (linhas 84-94).
- **Troca** `return "R_100"` final por `return None`, com log `❌ [DERIV] Ativo '<raw_symbol>' sem mapeamento reconhecido. Sinal descartado.` (mesmo nível/estilo do log já usado em `iqoption.py`).
- `get_deriv_symbol_map()` não muda.

### 2. `src/telegram_copier.py` (zona de alto risco)
Em `_parse_signal` (linha ~913-915), depois de `symbol = resolve_deriv_symbol(symbol)`: se `symbol is None`, descarta o sinal do mesmo jeito que a função já faz quando não consegue identificar nenhum símbolo (`if not symbol: return None`, linha 881-882) — mesmo padrão já existente na função, só estendido pro caso "identificou um símbolo cru, mas a Deriv não reconhece".

### 3. `src/routes/tradingview_bridge.py` (zona de alto risco)
`_map_symbol` passa a retornar `Optional[str]`. No handler do webhook, logo após `mapped_symbol = _map_symbol(symbol, broker_name)` (linha 474), se `None`: retorna `TradingViewWebhookResponse(status="rejected", message=f"Ativo '{symbol}' não reconhecido para Deriv — sinal descartado (sem execução em ativo diferente).")`, mirando o padrão de early-return já usado logo acima para `session_manager.can_trade()` (linhas 447-453) — sem chegar a conectar no broker nem enviar ordem.

### Arquivos tocados
- `src/broker/deriv_symbols.py`
- `src/telegram_copier.py` (zona de alto risco)
- `src/routes/tradingview_bridge.py` (zona de alto risco)

Sem migração de schema. IQ Option, Quotex e Pocket Option não passam por `resolve_deriv_symbol` — comportamento deles inalterado.

## Critérios de aceite

- [x] `resolve_deriv_symbol("XPTOZZZ")` (símbolo inventado) retorna `None`.
- [x] `resolve_deriv_symbol("EURUSD")` e `resolve_deriv_symbol("EURUSD-OTC")` continuam retornando `"R_100"` (mapeamento canônico preservado, não é fallback).
- [x] `resolve_deriv_symbol("R_75")` (já um símbolo Deriv) continua retornando `"R_75"` (passthrough preservado).
- [x] `resolve_deriv_symbol("EURUSDX")` — hoje cai no fallback por prefixo e retorna `"R_100"` — passa a retornar `None`.
- [x] `telegram_copier.py`: sinal com símbolo não mapeado pra Deriv não chega a chamar `send_order`/`async_send_order`; log de descarte aparece.
- [x] `tradingview_bridge.py`: webhook com símbolo não mapeado pra Deriv retorna `status="rejected"` com mensagem clara, sem chamar `_get_cached_broker` nem enviar ordem.
- [x] `grep -n '"R_100"' src/broker/deriv_symbols.py` só aparece no mapeamento canônico de `EURUSD`, nunca mais como retorno de fallback.
- [x] Fluxo de IQ Option, Quotex e Pocket Option inalterado (nenhum deles chama `resolve_deriv_symbol`).

## Impacto em performance

**Neutro ou levemente positivo.** `resolve_deriv_symbol` é síncrona, sem I/O, chamada uma vez por sinal recebido. O caminho "não mapeado" faz menos trabalho (early return em vez do loop de prefixos).

## Plano de rollback

`git revert` — sem migração de schema, sem dado persistido alterado. Efeito da reversão: sinal de ativo desconhecido na Deriv volta a ser executado em `R_100` (ou num palpite por prefixo) em vez de descartado.

## Aprovação

- [x] Revisado contra `docs/sdd/CONSTITUICAO.md` (§1 sem impacto de performance; §3 zona de alto risco — autorização explícita obrigatória; §7 autorização)
- [x] Aprovado explicitamente pelo usuário antes do início da implementação (2026-09-11)
