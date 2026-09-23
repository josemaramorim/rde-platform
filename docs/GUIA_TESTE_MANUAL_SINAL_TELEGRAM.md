# Guia — Teste manual de sinal (Telegram → ordem)

Este guia complementa [`scripts/README.md`](../scripts/README.md) (que documenta só o `send_test_signal.py`) com **tudo mais** que descobrimos ser necessário na sessão de 2026-09-23 pra rodar um teste manual do zero: configuração de ambiente, passo a passo completo, e os erros mais comuns que já apareceram.

## 1. Configuração de uma vez só (já feita nesta sessão)

Isso já está configurado no seu `.env` local — só precisa refazer se trocar de máquina ou o `.env` for perdido.

### 1.1. App do Telegram (my.telegram.org)

Desde a spec 017, `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` **não têm mais fallback com valor real** — são obrigatórios no `.env` (senão o app não sobe com `ENVIRONMENT=production`). Gerados em https://my.telegram.org/apps (app "Amorim" já criado). Valores já estão no `.env`:
```
TELEGRAM_API_ID=...
TELEGRAM_API_HASH=...
```
Se precisar gerar de novo (ex.: revogar por vazamento), é o mesmo app em my.telegram.org — não precisa criar um novo, só copiar `api_id`/`api_hash` de lá pro `.env`.

### 1.2. Canal de teste no Telegram

Canal criado: **"Teste RDE"** (ID `-1004415053620`), com a conta pessoal ("Amorim") como dono/admin — ela pode postar mensagens (necessário pro `send_test_signal.py`).

⚠️ Não adicione essa conta ao canal de produção também — desde a spec 016, o copier exige match **exato** de nome (normalizado), então não há mais risco de ambiguidade por estar nos dois, mas é mais simples manter as contas separadas mesmo assim.

### 1.3. Usuário RDE de teste

Não precisa criar um novo — `admin@rde-platform.com` já tem IQ Option conectado em modo **Demo**. Use esse.

## 2. Passo a passo do teste

### 2.1. Apontar o servidor pro canal de teste

`TELEGRAM_CHAT_ID`/`TELEGRAM_GROUP_NAME` no `.env` são **globais** (valem pra todos os usuários do servidor, não por usuário). Pra testar, troque temporariamente:
```
TELEGRAM_CHAT_ID=-1004415053620
```
(deixe um comentário no `.env` com o valor de produção original, pra não esquecer de reverter — ver passo 2.6.)

### 2.2. Reiniciar o backend

O `.env` só é lido no boot — o `--reload` do uvicorn recarrega o **código**, não o `.env`. Precisa matar e subir o processo de novo.

**Cuidado ao reiniciar** (aprendido do jeito difícil nesta sessão):
- O processo real é uma cadeia: reloader → worker → **subprocesso do copier** (via `multiprocessing`, um por usuário com copier ligado). Matar só o worker/reloader **não mata o subprocesso do copier** — ele fica órfão, rodando sozinho, e pode causar `database is locked` ou sessões duplicadas do Telegram na próxima subida.
- Sempre identifique a cadeia completa antes de matar (`Get-CimInstance Win32_Process -Filter "Name='python.exe'"`, olhando `ParentProcessId`) e mate na ordem: subprocesso do copier → worker → reloader.
- Depois de subir de novo, **confirme com um teste HTTP real** (`curl http://127.0.0.1:8000/docs`), não só "o processo existe" — um processo pode estar de pé e mesmo assim travado (ver seção de troubleshooting).

### 2.3. Conectar Telegram + ligar o copier

No dashboard, logado como `admin@rde-platform.com`:
1. "Conectar Telegram" com a conta "Amorim" (a mesma que criou o canal).
2. Ligar o copier.
3. Confirmar no Console de Logs (🖥️ botão no dashboard) que aparece algo como:
   ```
   🎯 [TELEGRAM] Canal ativo e monitorado exclusivamente: 'Teste RDE' (ID: -1004415053620)
   ```

### 2.4. Disparar o sinal de teste

No **PowerShell** (não bash — `export` não existe aqui, é `$env:VAR="valor"`):
```powershell
$env:TG_TEST_API_ID="..."       # mesmo api_id do passo 1.1
$env:TG_TEST_API_HASH="..."     # mesmo api_hash do passo 1.1
$env:TG_TEST_PHONE="+55..."     # numero da conta "Amorim"
python scripts/send_test_signal.py --channel "-1004415053620" --direction CALL --symbol EURUSD-OTC --timeframe M1
```
Primeira execução pede o código de login (SMS/app) no próprio terminal.

**Se o ativo escolhido estiver fechado** (`❌ [SINAL DESCARTADO] Ativo 'X' esta fechado/suspenso agora`), é o filtro de segurança funcionando (spec 014) — não é bug. Tente outro ativo (ex.: `BTCUSD-OTC`, cripto costuma estar sempre aberto) ou confira quais estão abertos no dashboard.

### 2.5. Acompanhar o resultado

Console de Logs do dashboard + saldo da conta demo. Se `get_contract_status` ficar "incerto" (a corretora demora a confirmar), o código agora tenta até 3x/9s antes de usar o saldo como árbitro (spec 019) — pode levar alguns segundos a mais que o normal nesse caso raro.

### 2.6. Reverter depois do teste

**Não esqueça este passo** — enquanto `TELEGRAM_CHAT_ID` apontar pro canal de teste, nenhum usuário real recebe sinal de produção.
```
TELEGRAM_CHAT_ID=-1001804981654   # valor de producao
```
E reinicie o backend de novo (mesmo cuidado do passo 2.2).

## 3. Problemas já vistos (e o que fazer)

| Sintoma | Causa | O que fazer |
|---|---|---|
| Backend todo travado (até `/docs` sem resposta) | `ThreadPoolExecutor` com thread presa numa reconexão à corretora — corrigido na spec 018, mas se acontecer de novo: | Matar a cadeia completa de processos (ver 2.2) e subir de novo. |
| `database is locked` no boot | Subprocesso órfão do copier de um restart anterior ainda com o banco aberto | Encontrar e matar o órfão (`Get-CimInstance ... | Where CommandLine -match 'multiprocessing'`) antes de subir de novo. |
| `AuthKeyUnregisteredError` / copier crasha com `CancelledError` | Sessão do Telegram invalidada — geralmente por ter matado o processo do copier à força (`Stop-Process -Force`) no meio de uma operação, corrompendo o arquivo de sessão | Reconectar o Telegram de novo pelo dashboard (gera sessão nova). |
| `Erro HTTP 400` no Console de Logs | Endpoint errado (`/admin/logs/copier` sem `user_id`) | Corrigido nas specs 012/015 — se voltar a acontecer, confirme que está usando o botão certo (por linha de usuário no Painel Admin, ou o Dashboard próprio). |
| Sinal "descartado" por ativo fechado | Comportamento esperado (spec 014) | Tentar outro ativo que esteja aberto. |
| Lucro de um WIN muito maior que o payout esperado | Corrigido na spec 019 (créditos atrasados da corretora não vazam mais pra ordem seguinte) | Se acontecer de novo com um valor > 2x o stake, o log vai mostrar o aviso de "profit limitado" — reportar se aparecer. |

## 4. Specs desta sessão (2026-09-23), pra contexto

| Spec | O que resolveu |
|---|---|
| [011](sdd/specs/011-fix-import-asyncio-refresh-balance.md) | `import asyncio` faltando zerava o saldo exibido no dashboard |
| [012](sdd/specs/012-fix-log-modal-admin-endpoint-dashboard.md) | Console de Logs do Dashboard próprio dando 400 |
| [013](sdd/specs/013-fix-sidebar-trava-modal-atras.md) | Sidebar sobrepondo modais em tela cheia (CSS) |
| [014](sdd/specs/014-fix-open-status-digital-timeout.md) | Filtro de ativo aberto/fechado nunca funcionava de verdade (busy-wait de 30s) |
| [015](sdd/specs/015-fix-admin-logs-por-usuario.md) | Console de Logs do Painel Admin dando 400 (botão global sem usuário) |
| [016](sdd/specs/016-fix-resolucao-canal-telegram-ambigua.md) | Resolução de canal Telegram por substring solta (risco de grudar no canal errado) |
| [017](sdd/specs/017-fix-telegram-api-credentials-hardcoded.md) | Credenciais reais do Telegram hardcoded no código |
| [018](sdd/specs/018-fix-threadpool-trava-event-loop.md) | `ThreadPoolExecutor` travando o backend inteiro |
| [019](sdd/specs/019-fix-calculo-lucro-vaza-entre-ordens.md) | Lucro de uma ordem vazando pra ordem seguinte quando status ficava incerto |
