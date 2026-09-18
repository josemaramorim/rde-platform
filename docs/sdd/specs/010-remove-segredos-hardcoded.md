# 010 — Remove fallbacks de segredo real em código/config versionados

- **Status:** Em revisão
- **Autor:** josemaramorim (via Claude)
- **Data:** 2026-09-17
- **Impedimento(s) relacionado(s):** IMP-013 (`docs/sdd/IMPEDIMENTOS.md`).
- **Zona de alto risco?** **Não** pela definição do `CLAUDE.md` (não toca `src/broker/*`, `telegram_copier.py`, `tradingview_bridge.py`, `executor.py`), mas é sensível por natureza (segredos/credenciais) e uma parte **tem risco real de quebrar um deploy em produção** se aplicada sem coordenação — ver seção "Ação necessária antes do deploy". Exige autorização explícita (Constituição §7).

## Problema

Valores de segredo reais (não placeholders óbvios) estão hardcoded como fallback em arquivos versionados:

1. **`docker-compose.yml` e `docker-compose.icp.yml`** — `POSTGRES_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_GROUP_NAME` têm valores reais como fallback (`${VAR:-valor_real}`). O `TELEGRAM_BOT_TOKEN` em especial é uma credencial de bot Telegram funcional, exposta permanentemente no histórico do git.
2. **`src/core/config.py`** — `ADMIN_PASSWORD` tem default `"admin123456"`, uma senha fraca e adivinhável, não um placeholder óbvio.
3. **`src/corrigir_admin.py`** e **`src/main.py`** (seed de startup) — cada um redeclara o **mesmo** fallback `"admin123456"` localmente, além do já existente em `config.py` (duplicação, viola também Constituição §2).
4. **`docs/GUIA_POSTGRESQL_E_ADMIN.md`** — documenta esses valores padrão em texto puro como "credenciais padrão", reforçando o uso do fallback em vez de configuração explícita.

Isso viola a Constituição §6 diretamente: *"Fallback, se existir, deve ser um valor obviamente inválido que força configuração explícita."*

## Contexto

O próprio projeto **já tem o padrão correto implementado** em dois outros campos — `JWT_SECRET_KEY` e `ENCRYPTION_KEY` (`src/core/config.py:90-99`): o default é uma string obviamente-placeholder (contém `"change-in-production"`), e um `field_validator` (`src/core/config.py:201-210`) rejeita esse placeholder especificamente quando `ENVIRONMENT == "production"` — sem quebrar `development`/local, onde o placeholder segue funcionando por conveniência. Esta spec estende exatamente esse padrão já estabelecido para `ADMIN_PASSWORD`, em vez de inventar um mecanismo novo.

Para `docker-compose.yml`/`.icp.yml` (YAML, fora do Pydantic) o equivalente é trocar o valor real do fallback por um placeholder obviamente inválido — o serviço então falha de forma visível (Postgres rejeita a senha, Telegram rejeita o token) se ninguém configurar o `.env` de verdade, em vez de operar silenciosamente com o valor real.

Não existe hoje um `.env.example` no repositório — os fallbacks no `docker-compose.yml` acabam sendo a única "documentação" de quais variáveis existem. Removê-los sem substituir por outra referência pioraria a descobribilidade. `.env.example` está atualmente no `.gitignore` (linha 79) — precisa de uma exceção (`!.env.example`), mesmo padrão já usado pra `docs/sdd/**`.

### ⚠️ Ação necessária antes do deploy (não é código)

Trocar o fallback do `docker-compose.yml`/`.icp.yml` por um placeholder **quebra qualquer ambiente que hoje dependa implicitamente do valor padrão** (não tem `POSTGRES_PASSWORD`/`TELEGRAM_BOT_TOKEN`/etc. explícito no `.env` de produção) — o Postgres não vai aceitar a nova senha-placeholder num volume já inicializado com a senha antiga, e o bot do Telegram para de autenticar. **Antes de aplicar esta parte da spec em produção**, confirme que o `.env` real do servidor já define essas 4 variáveis explicitamente (independente desta mudança). Se não define, defina antes do deploy — ou o serviço não sobe.

Separadamente, **o `TELEGRAM_BOT_TOKEN` atual deveria ser revogado e trocado por um novo (via BotFather)** — ele está exposto no histórico do git, e remover do código não apaga o histórico. Isso é uma ação sua, fora do escopo de código desta spec.

## Proposta

### 1. `src/core/config.py`
`ADMIN_PASSWORD` ganha um default placeholder óbvio (mesmo estilo de `JWT_SECRET_KEY`/`ENCRYPTION_KEY`) e um `field_validator` que rejeita esse placeholder (e o antigo `"admin123456"`) quando `ENVIRONMENT == "production"` — mesmo mecanismo já existente pros outros dois campos, sem código novo de infraestrutura.

### 2. `src/corrigir_admin.py` e `src/main.py`
Removem o fallback local duplicado (`getattr(settings, "ADMIN_PASSWORD", "admin123456") or "admin123456"`); passam a usar `settings.ADMIN_PASSWORD` diretamente — fonte única (Constituição §2), sem repetir o valor em mais de um lugar.

### 3. `docker-compose.yml` e `docker-compose.icp.yml`
`POSTGRES_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_GROUP_NAME` trocam o fallback real por um placeholder obviamente inválido (ex.: `CHANGE_ME_...`). **Só aplico esta parte depois da sua confirmação explícita** de que o `.env` de produção já define essas variáveis (ver "Ação necessária" acima).

### 4. `.env.example` (novo)
Lista as variáveis relevantes (nomes + placeholder/descrição, sem nenhum valor real) — passa a ser a referência de "o que configurar", no lugar dos fallbacks do `docker-compose.yml`. Precisa de `!.env.example` no `.gitignore` (que hoje ignora esse arquivo).

### 5. `docs/GUIA_POSTGRESQL_E_ADMIN.md`
Atualiza a seção de "credenciais padrão" — deixa de apresentar os valores como um default aceitável, aponta para `.env.example` e reforça que a senha de admin precisa ser definida explicitamente antes de subir em produção.

### Arquivos tocados
- `src/core/config.py`
- `src/corrigir_admin.py`
- `src/main.py`
- `docker-compose.yml`, `docker-compose.icp.yml` (condicional à sua confirmação)
- `.env.example` (novo)
- `.gitignore`
- `docs/GUIA_POSTGRESQL_E_ADMIN.md`

Sem migração de schema.

## Critérios de aceite

- [ ] `grep -rn "admin123456" src/` não encontra mais nenhuma ocorrência.
- [ ] `ADMIN_PASSWORD` com o placeholder padrão e `ENVIRONMENT=production` faz a app falhar ao subir com erro claro (mesmo teste que já existe implicitamente pra `ENCRYPTION_KEY`).
- [ ] `ADMIN_PASSWORD` com o placeholder padrão e `ENVIRONMENT=development` continua subindo normalmente (sem regressão no fluxo de dev local).
- [ ] `src/corrigir_admin.py` e `src/main.py` não têm mais `"admin123456"` local — usam `settings.ADMIN_PASSWORD`.
- [ ] (Se autorizado) `docker-compose.yml`/`.icp.yml` não têm mais os valores reais de `POSTGRES_PASSWORD`/`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`/`TELEGRAM_GROUP_NAME` como fallback.
- [ ] `.env.example` existe, versionado, sem nenhum valor real de segredo.
- [ ] `docs/GUIA_POSTGRESQL_E_ADMIN.md` não apresenta mais os valores como "credenciais padrão" a serem usadas como estão.
- [ ] `pytest tests/ -v` continua passando (nenhum teste depende do valor antigo de `ADMIN_PASSWORD`).
- [ ] Import de todos os módulos tocados limpo; app sobe sem erro em `ENVIRONMENT=development`.

## Impacto em performance

Nenhum — só validação de configuração no boot, não toca hot path.

## Plano de rollback

`git revert`. Sem migração de schema. Se a parte do `docker-compose.yml` já tiver sido deployada e algo quebrar por `.env` de produção não configurado a tempo, o rollback imediato é reverter o commit (volta pro fallback antigo) enquanto o `.env` correto é aplicado.

## Aprovação

- [ ] Revisado contra `docs/sdd/CONSTITUICAO.md` (§2 fonte única — remove duplicação do fallback; §6 segredos — objetivo central desta spec; §7 autorização)
- [ ] Confirmação explícita: `.env` de produção já define `POSTGRES_PASSWORD`/`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`/`TELEGRAM_GROUP_NAME` (necessário antes de tocar no `docker-compose.yml`/`.icp.yml`)
- [ ] Aprovado explicitamente pelo usuário antes do início da implementação
