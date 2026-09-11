# 002 — Namespace por usuário para PID/log do Telegram copier

- **Status:** Em revisão
- **Autor:** josemaramorim (via Claude)
- **Data:** 2026-09-11
- **Impedimento(s) relacionado(s):** IMP-001 (`docs/sdd/IMPEDIMENTOS.md`). Encosta em IMP-011 (dois endpoints legados mortos, propostos para remoção) e IMP-010 (`main.py` god file).
- **Zona de alto risco?** **Sim** — toca `src/telegram_copier.py` e várias rotas de `src/main.py` que controlam o subprocesso do copier. Exige autorização explícita antes da implementação (Constituição §3).

## Problema

`copier.pid` e `copier.log` são nomes de arquivo **fixos e globais** (sem namespace por usuário), usados como estado compartilhado entre todas as sessões do processo FastAPI. O escopo é maior do que o registrado originalmente em IMP-001:

1. **Um usuário pode matar o copier de outro.** `POST /copier/toggle` (`src/main.py:1206-1421`, endpoint real usado pelo frontend — `frontend/app/dashboard/page.tsx:175`) lê `pid_file = "copier.pid"` global. Se o usuário B chama toggle enquanto o copier do usuário A está rodando, o código interpreta o PID existente como "meu processo anterior" e o mata (`taskkill`/`SIGTERM`) antes de subir o dele (`src/main.py:1265-1298`).
2. **Vazamento de log entre usuários.** `GET /copier/logs` (`src/main.py:619-625`) é acessível a **qualquer usuário ativo** (não só admin) e lê `copier.log` — o mesmo arquivo global onde caem os logs do copier de todo mundo. Qualquer usuário logado consegue ler o log de execução (incluindo mensagens de erro, ativos operados, etc.) de outros usuários.
3. **Status incorreto no dashboard.** `GET /dashboard/live` (`src/main.py:734-748`) e `GET /telegram/status` (`src/main.py:446-480`, usado por `dashboard`, `perfil`, `setup` e `admin` no frontend) checam a existência do `copier.pid` global — um usuário vê `copier_running: true` mesmo quando é o copier de **outro** usuário que está de pé, e o seu está parado.
4. **O próprio subprocesso reforça o problema.** `src/telegram_copier.py::_write_pid()` (linha 1217-1223, chamado após o broker conectar) reescreve `copier.pid` com o PID do processo atual — mesmo comportamento global, agora também na zona de alto risco.
5. **Escrita de log fora do padrão em mais um lugar.** `src/routes/telegram_auth.py:_update_user_live_status` (linha 71-76) grava no `copier.log` global durante o fluxo de autenticação Telegram.
6. **Dois endpoints legados com o mesmo bug, e mortos.** `POST /telegram/start-copier` e `POST /telegram/stop-copier` (`src/main.py:483-556`) implementam a mesma lógica (com o mesmo `copier.pid` global) mas **não são chamados por nenhuma página do frontend** — `/copier/toggle` os substituiu. Continuam expostos na API (ex.: via Swagger/chamada direta), então mesmo corrigindo tudo o resto, alguém chamando essas rotas diretamente ainda mataria o copier de outro usuário.

O padrão de namespace por usuário **já existe** no mesmo arquivo para outros estados do copier — `live_status_{user.id}.json` e `live_operations_{user.id}.json` (`src/main.py:713-714`) — só não foi aplicado ao PID e ao log.

## Contexto

O copier roda como **subprocesso por usuário** (`src/telegram_copier.py`, spawnado via `subprocess.Popen` com `--user-id`), mas o único jeito de rastrear "esse subprocesso está vivo" e "onde está o log dele" hoje é um nome de arquivo fixo no diretório de trabalho do processo pai. Isso funciona com um único usuário ativo por vez; com dois ou mais, o segundo a chamar `/copier/toggle` corrompe o estado do primeiro.

Este impedimento é P0 porque é dinheiro real: matar a sessão de outro usuário no meio de uma operação pode deixar uma entrada aberta sem o copier vivo para processar o resultado, e o vazamento de log expõe dados operacionais de um usuário para outro.

## Proposta

Aplicar o mesmo padrão já usado em `live_status_{user.id}.json`: **`copier_{user_id}.pid`** e **`copier_{user_id}.log`**.

### 1. `src/telegram_copier.py`
- `_write_pid()` passa a escrever em `f"copier_{self._user_id}.pid"`.

### 2. `src/routes/telegram_auth.py`
- `_update_user_live_status(user_id, ...)` já recebe `user_id` — passa a gravar em `f"copier_{user_id}.log"`.

### 3. `src/main.py`
- `POST /copier/toggle` — `pid_file` e o log do `Popen` passam a usar `f"copier_{user.id}.pid"` / `f"copier_{user.id}.log"`.
- `GET /dashboard/live` e `GET /telegram/status` — checam `f"copier_{user.id}.pid"` (o do próprio usuário).
- `_read_copier_log_lines` passa a receber `user_id` e ler `f"copier_{user_id}.log"`.
- `GET /copier/logs` — passa o `user.id` de quem chama (fecha o vazamento: cada usuário só lê o próprio log).
- `GET /admin/logs/copier` e `DELETE /admin/logs/copier` — passam a exigir `user_id` como query param (`400` com mensagem clara se ausente), já que não existe mais um único log global para "todos".
- Limpeza de PID stale no `startup()` — troca o `os.path.exists("copier.pid")` único por um `glob.glob("copier_*.pid")`, validando/limpando cada um individualmente (mesma lógica de hoje, por arquivo).
- **Remove** `POST /telegram/start-copier` e `POST /telegram/stop-copier` — confirmados não usados pelo frontend (`frontend/app/dashboard/page.tsx` chama só `/copier/toggle`), duplicam a lógica do endpoint real e, se deixados como estão, continuariam sendo uma forma de matar o copier de outro usuário mesmo depois desta correção. Resolve também um item do IMP-011 (código morto).

### Arquivos tocados
- `src/telegram_copier.py` (zona de alto risco)
- `src/main.py` (god file — edição espalhada em ~8 pontos, todos só troca de nome de arquivo/adição de parâmetro, sem mudar a lógica de negócio)
- `src/routes/telegram_auth.py`

Sem migração de schema. Sem broker/executor tocados.

### Nota operacional para o deploy

Um copier **já em execução** no momento do deploy foi spawnado escrevendo no `copier.pid` antigo (global). Depois do deploy, a API passa a procurar `copier_{user_id}.pid` e não vai encontrar esse processo — o dashboard mostrará "parado" para esse usuário mesmo com o processo antigo ainda rodando em background (órfão). Recomenda-se **parar todos os copiers ativos antes do deploy** (ou aceitar que, para quem estava com o copier ligado no momento exato do deploy, será necessário um "stop" manual do processo órfão uma vez, via `taskkill`/`kill` no PID reportado em `copier.pid` antigo, se o arquivo ainda existir).

## Critérios de aceite

- [ ] `grep -rn '"copier\.pid"\|"copier\.log"' src/` não encontra mais nenhuma ocorrência do nome global fixo.
- [ ] Dois usuários de teste: A liga o copier (`/copier/toggle`, `active=true`) → cria `copier_<A>.pid`/`copier_<A>.log`. B liga o copier em seguida → cria `copier_<B>.pid`/`copier_<B>.log` **sem** matar o processo de A (`psutil.pid_exists` no PID de A continua `True`).
- [ ] B desliga o copier (`active=false`) → só o processo de B morre; A continua rodando.
- [ ] `GET /copier/logs` de B não retorna nenhuma linha do log de A.
- [ ] `GET /telegram/status` e `GET /dashboard/live` de B reportam `copier_running=false` enquanto só o de A está rodando.
- [ ] `GET /admin/logs/copier` sem `user_id` retorna `400` com mensagem clara; com `user_id` retorna o log daquele usuário.
- [ ] Ao subir o app com arquivos `copier_<X>.pid` stale (processo morto), a limpeza do `startup()` remove cada um sem tocar em `copier_<Y>.pid` de um processo vivo.
- [ ] `POST /telegram/start-copier` e `POST /telegram/stop-copier` não existem mais (404); `/copier/toggle` continua funcionando normalmente para start/stop.
- [ ] App sobe sem erro; fluxo completo `/copier/toggle` on → sinal de teste → off testado manualmente em ambiente de dev com pelo menos 2 usuários simultâneos.

## Impacto em performance

**Neutro.** Mesmo número de operações de I/O de arquivo por requisição — só o nome do arquivo passa a ser parametrizado por `user_id` em vez de fixo. O `glob` no startup é único, fora do hot path de disparo de ordem.

## Plano de rollback

- Reverter o commit (`git revert`). Não há migração de schema.
- Risco na volta: se algum copier foi iniciado já com o nome novo (`copier_{user_id}.pid`) e o revert volta a procurar o nome global antigo, o mesmo problema de "processo órfão invisível" da nota operacional acima se repete no sentido inverso — mitigação é a mesma: parar copiers ativos antes de reverter, ou aceitar um `taskkill` manual pontual.

## Aprovação

- [ ] Revisado contra `docs/sdd/CONSTITUICAO.md` (§1 sem impacto de performance; §3 zona de alto risco — autorização explícita obrigatória; §5 remoção de código morto ambíguo; §7 autorização)
- [ ] Aprovado explicitamente pelo usuário antes do início da implementação
