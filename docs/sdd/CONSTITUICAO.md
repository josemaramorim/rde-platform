# Constituição do RDE_5

Regras não-negociáveis para qualquer mudança no projeto. Uma spec (ver [`README.md`](README.md)) que viole alguma destas regras deve justificar explicitamente a exceção e ser aprovada como exceção, não silenciosamente ignorada.

## 1. Performance-first

O requisito não-funcional mais importante do projeto é latência de disparo de ordem. Isso significa:

- **Nenhuma chamada de rede ou DB bloqueante dentro de código `async` sem offload explícito** (`run_in_executor`/`asyncio.to_thread`). Isso vale em especial para qualquer método chamado a partir de um event loop compartilhado por múltiplos usuários (ex.: rotas FastAPI, `tradingview_bridge.py`) — um `time.sleep`/chamada síncrona ali trava *todos* os usuários, não só um.
- Toda nova integração de corretora (`src/broker/*`) precisa expor uma versão `async_*` real (não um wrapper que bloqueia a thread via `run_async`) para qualquer método que possa ser chamado no hot path ou em heartbeat/polling.
- Timeouts, intervalos de polling e janelas de espera devem ser configuráveis ou pelo menos centralizados e comentados com o motivo do valor escolhido — nunca uma constante mágica solta no meio do código (ex.: um `sleep(62)` hardcoded).
- Logging no hot path de execução de trade deve ser mínimo e não deve fazer I/O síncrono bloqueante por linha. Log verboso é para debug local, não para o caminho de produção que dispara ordens.

## 2. Fonte única da verdade

- Regras de negócio (ex.: mapeamento plano → corretoras permitidas, limites por plano, regras de martingale/ciclo de risco) vivem em **um único lugar** no código. Scripts de seed, endpoints de admin e lógica de negócio devem ler dessa fonte única — nunca redeclarar a regra em paralelo.
- Se uma regra precisa ser corrigida "na mão" via endpoint ou script (como o `fix-plan-brokers` de hoje), isso é sinal de que existe uma duplicação a ser eliminada, não uma solução definitiva — deve virar um impedimento em `IMPEDIMENTOS.md`.

## 3. Zona de alto risco exige spec + autorização explícita

Mudanças em `src/broker/*`, `src/telegram_copier.py`, `src/routes/tradingview_bridge.py` e `src/executor.py` (tudo que manda ordem real para uma corretora ou decide quanto apostar) exigem:
1. Uma spec aprovada (ver `README.md`).
2. Autorização explícita do usuário antes de qualquer edição de código, mesmo para uma mudança de uma linha.

## 4. Código limpo

- Type hints obrigatórios em toda função nova ou editada de forma relevante.
- Proibido `except Exception: pass` silencioso. Se uma exceção pode legitimamente ser ignorada, ela é logada com contexto (o que falhou, com qual dado) antes de continuar.
- Nenhuma duplicação de método/constante dentro do mesmo arquivo (ex.: um método definido duas vezes) passa em revisão.
- Um arquivo que ultrapassa ~500 linhas e mistura mais de uma responsabilidade clara (rotas + migração + seed + regra de negócio, por exemplo) é candidato a quebra — registrar como impedimento em vez de continuar crescendo.

## 5. Sem código morto ambíguo

- Código não referenciado por nenhum caminho de execução real (nenhum import, nenhuma rota registrada) deve ser removido ou explicitamente marcado como propositalmente mantido (com um comentário dizendo por quê e até quando). Não deve ficar apenas "esquecido" no repositório — isso confunde quem lê o código depois e gera risco de alguém reconectar a peça errada.

## 6. Segredos e artefatos

- Nenhum segredo (token, senha, chave) com valor real como fallback hardcoded em arquivo versionado (código-fonte ou `docker-compose*.yml`). Fallback, se existir, deve ser um valor obviamente inválido que force configuração explícita.
- Binários e builds empacotados (executáveis, DLLs, bundles de runtime) não são versionados no git — vão como artefato de release/distribuição, fora do histórico do repositório.

## 7. Nada muda sem autorização

Nenhuma mudança em arquivos de código de aplicação (`src/`, `frontend/`) acontece sem autorização explícita do usuário para aquela mudança específica — aprovação de uma spec ou de um plano anterior não é autorização permanente para mudanças futuras não descritas nele.

## 8. Toda mudança vive numa branch própria

Nenhum commit de implementação (spec aprovada virando código, correção de bug, refactor, e também mudanças de configuração/processo como esta constituição) vai direto para `main` ou `develop`. Regras:

- Antes de implementar, criar uma branch a partir da `main` atualizada: `git checkout -b <tipo>/<slug-curto>` (ex.: `fix/pid-copier-por-usuario`, `chore/sdd-setup`, `feat/async-balance-deriv`). Tipos: `fix`, `feat`, `perf`, `refactor`, `chore`, `docs`.
- A branch referencia a spec quando houver uma (nome da branch ou primeira linha da descrição do PR aponta para `docs/sdd/specs/NNN-*.md`).
- `main`/`develop` só recebem a mudança via merge/PR depois de revisão — nunca commit direto nelas, nem para "coisa pequena". Push para `main`/`develop` (ou merge nelas) exige autorização explícita do usuário, assim como a implementação em si.
- Branches de manutenção do próprio processo (ex.: atualizar este arquivo) seguem a mesma regra — sem exceção para "é só documentação".
