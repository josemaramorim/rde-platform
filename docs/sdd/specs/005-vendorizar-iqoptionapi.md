# 005 — Vendorizar `iqoptionapi` (fixar dependência dentro do repo)

- **Status:** Implementado (PR #15, mergeado em 2026-09-11)
- **Autor:** josemaramorim (via Claude)
- **Data:** 2026-09-11
- **Impedimento(s) relacionado(s):** Nenhum aberto diretamente — proposta motivada por pergunta do usuário sobre organizar libs de corretora em pastas próprias. Registra e deixa fora de escopo o IMP-015 (Quotex/Pocket Option), achado durante a exploração.
- **Zona de alto risco?** **Sim** — `src/broker/iqoption.py` está na zona de alto risco, e mesmo sem editar esse arquivo, qualquer diferença na lib que ele importa afeta diretamente o disparo de ordens reais na IQ Option. Exige autorização explícita antes da implementação (Constituição §3).

## Problema

`iqoptionapi` é instalado hoje via `requirements.txt` como:

```
iqoptionapi @ git+https://github.com/Lu-Yi-Hsun/iqoptionapi.git
```

Sem pin de commit/tag — **rastreia a branch** do repositório. Cada `pip install` (build Docker, setup local novo) pode trazer um código diferente do que foi testado, sem aviso nenhum. É um repositório pequeno, de manutenção individual (não é um pacote oficial da corretora), sem arquivo de licença empacotado — ou seja, reprodutibilidade de build depende inteiramente da disponibilidade e do conteúdo atual de um GitHub de terceiro.

## Contexto

Levantamento de quais corretoras realmente usam lib externa, feito a pedido do usuário:

| Corretora | É lib externa? | Situação atual |
|---|---|---|
| IQ Option | Sim — `iqoptionapi` | Instalada via git, sem pin (o problema desta spec). |
| Deriv | **Não** | `src/broker/deriv.py` é código próprio do projeto (usa `websockets`/`requests` direto) — nada a vendorizar. |
| Quotex | Sim — `quotexpy` | **Ausente de `requirements.txt` e do `Dockerfile`** — corretora provavelmente não funciona em produção. Registrado como **IMP-015** (novo, ver `IMPEDIMENTOS.md`), fora do escopo desta spec. |
| Pocket Option | Sim — `pocketoptionapi-async` | Mesma situação de Quotex — parte do IMP-015. |

`iqoptionapi` é pequena (728KB, 65 arquivos `.py`), então vendorizar não tem o mesmo peso do problema já registrado em IMP-012 (binários de ~94MB em `cliente/`). O pacote declara como dependências `requests`, `pylint` e **`websocket-client==0.56`** — uma versão bem antiga (~2020); isso já é uma característica da lib hoje (via pip), não algo que a vendorização piora, mas vale registrar como risco conhecido pra quem for mexer nela depois.

Esta spec cobre só o `iqoptionapi`. Quotex/Pocket Option ficam de fora — primeiro precisa decidir (fora desta spec) se essas corretoras voltam a ser instaladas normalmente via pip; só faz sentido vendorizar depois disso, se for o caso.

## Proposta

### 1. Nova pasta `vendor/iqoptionapi/`
Clone congelado do repositório `https://github.com/Lu-Yi-Hsun/iqoptionapi`, pinado num commit específico — inclui o `setup.py` original do projeto (necessário pra instalação local) e o pacote `iqoptionapi/`. Adiciona `vendor/iqoptionapi/VENDORED.md` com: repositório de origem, commit/hash vendorizado, data, e a licença do projeto original se ela existir no repo fonte (checar antes de vendorizar; se não existir, documentar essa ausência).

### 2. `requirements.txt`
Troca:
```
iqoptionapi @ git+https://github.com/Lu-Yi-Hsun/iqoptionapi.git
```
por instalação local editável:
```
-e ./vendor/iqoptionapi
```
Continua se comportando como um pacote Python normal (`import iqoptionapi` funciona igual) — só a origem muda de GitHub pra uma pasta do próprio repo.

### 3. `Dockerfile`
Ajusta a ordem de `COPY` pra incluir `vendor/` **antes** do `pip install -r requirements.txt` (hoje só `requirements.txt` é copiado antes, pra aproveitar cache de camada; `-e ./vendor/iqoptionapi` precisa que a pasta já esteja presente nesse passo).

### 4. `src/broker/iqoption.py`
**Nenhuma mudança.** `from iqoptionapi.stable_api import IQ_Option` continua idêntico — esse é o objetivo: trocar a origem da dependência sem tocar em quem a usa.

### Arquivos tocados
- `vendor/iqoptionapi/` (novo — ~728KB, ~65 arquivos)
- `requirements.txt`
- `Dockerfile`
- `docs/sdd/IMPEDIMENTOS.md` (registro do IMP-015, já incluído nesta branch)

## Critérios de aceite

- [x] `vendor/iqoptionapi/` existe com o pacote completo e `VENDORED.md` documentando origem/commit.
- [x] `requirements.txt` não referencia mais `git+https://github.com/...` para o iqoptionapi.
- [x] `pip install -r requirements.txt` num ambiente limpo instala `iqoptionapi` a partir da pasta local (checável por `pip show iqoptionapi` apontando pra dentro do repo, não pra um cache de git).
- [x] `import iqoptionapi` e `from iqoptionapi.stable_api import IQ_Option` continuam funcionando sem nenhuma edição em `src/broker/iqoption.py`.
- [x] `docker build` continua funcionando com a nova ordem de `COPY` — validado com build real (Docker Desktop), incluindo `docker run` confirmando `import iqoptionapi` resolvendo para `/app/vendor/iqoptionapi/` dentro do container.
- [x] Testado manualmente: instanciar `IQOptionBroker`, conectar e chamar `get_balance()`/`async_get_balance()` com uma conta de teste — mesmo resultado de antes da mudança.

## Impacto em performance

Neutro em runtime — mesma lib, mesmo código, só muda de onde é instalada (não afeta o hot path de disparo de ordem). Build Docker pode ficar levemente mais rápido (sem depender de clonar do GitHub a cada build) — efeito colateral positivo, não o objetivo.

## Plano de rollback

`git revert`. Reverte `requirements.txt` pra URL git original; sem dado persistido alterado.

## Aprovação

- [x] Revisado contra `docs/sdd/CONSTITUICAO.md` (§3 zona de alto risco — autorização explícita obrigatória; §6 artefatos — vendorizar uma lib pequena não é o mesmo problema do IMP-012, mas segue o mesmo princípio de justificar o que é versionado; §7 autorização)
- [x] Aprovado explicitamente pelo usuário antes do início da implementação (2026-09-11)
