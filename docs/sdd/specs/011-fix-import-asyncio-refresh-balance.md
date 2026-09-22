# 011 — Corrige `NameError` em `refresh_balance` que zera o saldo exibido

- **Status:** Em revisão
- **Autor:** josemaramorim (via Claude)
- **Data:** 2026-09-22
- **Impedimento(s) relacionado(s):** Nenhum registrado ainda em `IMPEDIMENTOS.md` — bug encontrado nesta sessão a partir de um relato do usuário (dashboard mostrando saldo $0.00 com IQOption conectada).
- **Zona de alto risco?** **Não** pela definição formal do `CLAUDE.md`/Constituição §3 (não toca `src/broker/*`, `telegram_copier.py`, `tradingview_bridge.py`, `executor.py` — o arquivo é `src/routes/broker.py`). Ainda assim, por ser `src/` e mudar comportamento observável, segue a regra 3 do `CLAUDE.md`: spec + autorização explícita antes do código, mesmo sendo 1 linha.

## Problema

`POST /broker/refresh-balance` (`src/routes/broker.py:481-658`, função `refresh_balance`) usa `asyncio.get_running_loop()`, `asyncio.wait_for`, `asyncio.gather` e `ThreadPoolExecutor` (linhas 599-604) sem que `asyncio` nem `ThreadPoolExecutor` estejam importados nesse escopo — nem no topo do arquivo, nem localmente dentro da própria função (diferente de outras duas funções do mesmo arquivo, `test_broker_connection` linhas 368-369 e outra rota linha 701-702, que importam ambos localmente antes de usar).

Isso gera `NameError: name 'asyncio' is not defined` em toda chamada, capturado pelo `except Exception as pool_err` genérico (linha 607-609), que loga o erro mas zera `raw_results = []` e segue o fluxo normalmente — sem propagar erro ao chamador. Resultado: `setting.balance` nunca é atualizado no banco, e o dashboard (`/dashboard/live` em `src/main.py`, que só lê `BrokerSetting.balance` do banco) exibe `$0.00` mesmo com a corretora conectada.

Confirmado em `trades.log` de hoje (2026-09-22), repetindo a cada ciclo de refresh:
```
2026-09-22 15:13:30,332 | ERROR | Erro no pool de busca de saldos: name 'asyncio' is not defined
2026-09-22 15:14:58,722 | ERROR | Erro no pool de busca de saldos: name 'asyncio' is not defined
```

## Contexto

O padrão de import local dentro da função (em vez de módulo-level) já existe duas vezes no mesmo arquivo (`broker.py:368-369` e `broker.py:701-702`) — a spec segue esse padrão já estabelecido no arquivo em vez de introduzir um novo (ex.: mover pra import de módulo), para manter a mudança mínima e o diff pequeno.

Não há teste automatizado cobrindo esta rota (IMP-006, ausência de suíte de testes) — o bug ficou invisível até um usuário reportar o saldo zerado; o log de erro existia mas ninguém monitora `trades.log` ativamente.

## Proposta

### `src/routes/broker.py`
Dentro da função `refresh_balance` (antes do bloco `try:` na linha 598), adiciona:
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor
```
Nenhuma outra mudança de lógica — só resolve o `NameError`.

### Arquivos tocados
- `src/routes/broker.py` (1 função, 2 linhas adicionadas)

Sem migração de schema.

## Critérios de aceite

- [ ] `POST /broker/refresh-balance` não gera mais `NameError: name 'asyncio' is not defined` (verificado manualmente via chamada à rota com uma corretora demo configurada).
- [ ] Após o refresh, `BrokerSetting.balance` no banco reflete o saldo real da corretora (verificado consultando o banco ou observando o dashboard atualizar de `$0.00` para o valor real).
- [ ] `trades.log` deixa de registrar `Erro no pool de busca de saldos: name 'asyncio' is not defined` após o fix.
- [ ] Import do módulo limpo; app sobe sem erro em `ENVIRONMENT=development`.

## Impacto em performance

Nenhum — só corrige um erro que impedia o código (já assíncrono, via `ThreadPoolExecutor`/`asyncio.gather`) de rodar. Não adiciona nem remove chamadas de rede/DB, só permite que as que já existiam no design (spec 004, mesmo padrão de offload) efetivamente executem.

## Plano de rollback

`git revert` — mudança de 2 linhas, sem estado persistido alterado além do `BrokerSetting.balance` passar a ser atualizado corretamente (o que é o comportamento desejado, não um risco).

## Aprovação

- [ ] Revisado contra `docs/sdd/CONSTITUICAO.md` (§7 autorização)
- [ ] Aprovado explicitamente pelo usuário antes do início da implementação
