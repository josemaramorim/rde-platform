# 018 — ThreadPoolExecutor com `with` trava o processo inteiro em timeout

- **Status:** Em revisão
- **Autor:** josemaramorim (via Claude)
- **Data:** 2026-09-23
- **Impedimento(s) relacionado(s):** Nenhum registrado ainda — incidente real observado nesta sessão (app parou de responder por completo, `GET /docs` incluso).
- **Zona de alto risco?** **Não** pela definição formal do `CLAUDE.md` (não toca `src/broker/*`, `telegram_copier.py`, `tradingview_bridge.py`, `executor.py`; toca `src/main.py` e `src/routes/broker.py`). Ainda assim, por ser `src/` e mudar comportamento observável (timeout de rotas), segue a regra 3: spec + autorização explícita.

## Problema

Em 2026-09-23 ~15:44-15:47, o backend parou de responder **por completo** — até `GET /docs` (rota que não toca corretora nem Telegram) deu timeout. Rastreado para 4 pontos que usam o mesmo padrão perigoso:

```python
with ThreadPoolExecutor(...) as pool:
    result = await asyncio.wait_for(loop.run_in_executor(pool, fn), timeout=X)
```

Quando o `asyncio.wait_for` estoura o timeout, a *espera* é abandonada, mas a thread de `fn` continua rodando de verdade no `ThreadPoolExecutor`. Ao sair do bloco `with` (inclusive no caminho do `except TimeoutError`), `ThreadPoolExecutor.__exit__` chama `shutdown(wait=True)` **de forma síncrona, na própria thread do event loop** — bloqueia até a thread realmente terminar. Se a thread nunca termina, **o event loop inteiro trava para sempre**, impedindo até requisições sem nenhuma relação (como `/docs`) de serem atendidas.

Uma thread pode nunca terminar porque a lib vendorizada da IQ Option (`vendor/iqoptionapi/iqoptionapi/api.py:730` `start_websocket` e `:754` `send_ssid`) tem loops de espera ativa (`while ...: pass`) **sem timeout nenhum** — mesma classe de bug já corrigida na spec 014 (`get_digital_underlying_list_data`), mas em dois outros pontos. No incidente, a corretora derrubou a conexão (`WinError 10054` repetido no log) durante uma tentativa de reconexão disparada por `/broker/refresh-balance`, prendendo a thread num desses loops.

**4 ocorrências do padrão:**
1. `src/main.py:252-257` — sem `wait_for` nenhum (nem a espera é limitada).
2. `src/routes/broker.py:445-453` (`test-connection`) — `wait_for(timeout=35.0)`.
3. `src/routes/broker.py:601-612` (`refresh-balance`) — `wait_for(timeout=25.0)`. **Foi o gatilho do incidente real.**
4. `src/routes/broker.py:753-756` (`test-trade`) — sem `wait_for` nenhum. É o mais grave: dispara ordem de teste real, sem limite de espera algum.

## Contexto

Não é necessário mexer em `src/broker/*` nem na lib vendorizada pra resolver o **travamento total** — isso é consequência de como o `ThreadPoolExecutor` é usado nas rotas, não da causa da thread travar em si (essa é outra spec, se o usuário quiser tratar separadamente: adicionar timeout dentro dos loops do `api.py` vendorizado). Aqui o objetivo é: mesmo que uma thread trave para sempre lá dentro, **isso nunca mais deve travar o processo inteiro** — o pior caso vira "uma thread órfã fica presa em segundo plano" (recurso desperdiçado, mas não um apagão pra todos os usuários).

## Proposta

Nos 4 pontos, troca o `with ThreadPoolExecutor(...) as pool:` por uma instância sem context manager, sem `shutdown()` bloqueante — o pool e qualquer thread presa dentro dele ficam órfãos em segundo plano em vez de travar quem está esperando:

```python
# Antes
with ThreadPoolExecutor(max_workers=N) as pool:
    try:
        result = await asyncio.wait_for(loop.run_in_executor(pool, fn), timeout=X)
    except asyncio.TimeoutError:
        ...

# Depois
pool = ThreadPoolExecutor(max_workers=N)
try:
    result = await asyncio.wait_for(loop.run_in_executor(pool, fn), timeout=X)
except asyncio.TimeoutError:
    ...
```

Adicionalmente, os dois pontos sem `wait_for` (`main.py:254` e `broker.py:755`) ganham um timeout explícito, mesmo padrão já usado nos outros dois (`test-trade`, que dispara ordem, usa 35s — igual ao `test-connection`; `main.py`, que só busca saldo, usa 25s — igual ao `refresh-balance`).

### Arquivos tocados
- `src/main.py` (1 função)
- `src/routes/broker.py` (3 funções: `test_broker_connection`, `refresh_balance`, `test_trade`)

Sem migração de schema, sem mudança de comportamento observável no caminho feliz (só no caminho de timeout/thread travada).

## Critérios de aceite

- [ ] Simulando uma thread que nunca retorna (ex.: `time.sleep(999)` num teste manual local), o `wait_for` estoura no tempo configurado e a rota responde com o erro de timeout **imediatamente** — sem travar outras requisições concorrentes (`/docs` continua respondendo durante o teste).
- [ ] `main.py:254` e `broker.py:755` passam a ter timeout explícito (25s e 35s respectivamente).
- [ ] Comportamento no caminho feliz (sem timeout) inalterado nos 4 pontos.
- [ ] Import de todos os módulos tocados limpo; app sobe sem erro.

## Impacto em performance

**Objetivo central: elimina um cenário de negação de serviço total** (o processo inteiro trava, não só uma rota) quando uma chamada de rede à corretora demora demais ou nunca retorna — ataca diretamente o requisito não-funcional #1 (latência/disponibilidade de disparo de ordem). Nenhuma chamada de rede nova adicionada.

## Plano de rollback

`git revert` — mudança de padrão de código, sem estado persistido alterado. Threads órfãs deixadas por trás (no pior caso) são limpas quando o processo Python encerra.

## Aprovação

- [ ] Revisado contra `docs/sdd/CONSTITUICAO.md` (§1 performance-first — objetivo central; §7 autorização)
- [ ] Aprovado explicitamente pelo usuário antes do início da implementação
