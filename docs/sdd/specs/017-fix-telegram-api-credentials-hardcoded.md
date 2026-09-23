# 017 — Remove TELEGRAM_API_ID/API_HASH reais hardcoded (IMP-013)

- **Status:** Em revisão
- **Autor:** josemaramorim (via Claude)
- **Data:** 2026-09-23
- **Impedimento(s) relacionado(s):** IMP-013 (`docs/sdd/IMPEDIMENTOS.md`) — nova ocorrência do mesmo padrão, em arquivos que a lista original do IMP-013 não cobria.
- **Zona de alto risco?** **Sim** — toca `src/telegram_copier.py` (mesmo sem mudar lógica de execução de sinal, é o arquivo listado na Constituição §3). `src/core/config.py` não está na lista formal, mas a mudança é uma unidade só com a de `telegram_copier.py`. Exige autorização explícita antes de qualquer edição (Constituição §3).

## Problema

`src/core/config.py:168-169` define os defaults do Pydantic Settings com **valores reais**, não placeholders:
```python
TELEGRAM_API_ID: int = Field(default=24906269, description="Telegram API ID")
TELEGRAM_API_HASH: str = Field(default="4826f9dd0be48b617f94fc04b88ffabc", description="Telegram API Hash")
```
`src/telegram_copier.py:56-57` **duplica** os mesmos valores reais como fallback local, redundante com o default acima (viola também Constituição §2, fonte única):
```python
self.api_id = settings.TELEGRAM_API_ID or 24906269
self.api_hash = settings.TELEGRAM_API_HASH or "4826f9dd0be48b617f94fc04b88ffabc"
```
Esses valores são credenciais reais de app do Telegram (geradas em my.telegram.org), expostas permanentemente no histórico do git — mesmo padrão do IMP-013, mas em campos que a lista original desse impedimento não incluía.

## ⚠️ Ação necessária antes de aplicar (não é código)

O `.env` local deste ambiente tem **`ENVIRONMENT=production`** e **não define** `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` explicitamente — depende inteiramente do fallback acima. Seguindo o mesmo padrão já usado pro `SECRET_KEY`/`ENCRYPTION_KEY` (validação que rejeita o placeholder quando `ENVIRONMENT == "production"`), **este ambiente vai parar de subir** assim que a spec for aplicada, até que `TELEGRAM_API_ID` e `TELEGRAM_API_HASH` reais sejam definidos no `.env`.

**Antes de aplicar esta spec:** gere (ou reaproveite, se já tiver) um par API_ID/API_HASH em https://my.telegram.org e defina no `.env`:
```
TELEGRAM_API_ID=...
TELEGRAM_API_HASH=...
```
Separadamente — o par atual (`24906269` / `4826f9dd0be48b617f94fc04b88ffabc`) já está exposto no histórico do git; vale gerar um novo em vez de só copiar o antigo pro `.env`, já que remover do código não apaga o histórico.

## Proposta

### 1. `src/core/config.py`
Troca os defaults por placeholders obviamente inválidos e adiciona validators que rejeitam o placeholder quando `ENVIRONMENT == "production"` — mesmo mecanismo já usado pro `SECRET_KEY`/`ENCRYPTION_KEY` (linhas 190-210), sem inventar padrão novo:
```python
TELEGRAM_API_ID: int = Field(default=0, description="Telegram API ID (my.telegram.org) -- 0 forca configuracao explicita")
TELEGRAM_API_HASH: str = Field(default="change-in-production-telegram-api-hash", description="Telegram API Hash (my.telegram.org)")
```
```python
@field_validator("TELEGRAM_API_ID")
@classmethod
def validate_telegram_api_id(cls, v: int, info) -> int:
    env = info.data.get("ENVIRONMENT", "development")
    if env == "production" and v <= 0:
        raise ValueError("❌ TELEGRAM_API_ID não foi configurado! Gere o seu em https://my.telegram.org")
    return v

@field_validator("TELEGRAM_API_HASH")
@classmethod
def validate_telegram_api_hash(cls, v: str, info) -> str:
    env = info.data.get("ENVIRONMENT", "development")
    if env == "production" and (not v or "change-in-production" in v.lower()):
        raise ValueError("❌ TELEGRAM_API_HASH não foi alterado! Gere o seu em https://my.telegram.org")
    return v
```
Em `development`, o placeholder segue subindo sem erro (mesma convenção do `SECRET_KEY`) — mas, diferente de `SECRET_KEY` (uma chave de assinatura JWT interna que funciona com qualquer valor), um placeholder de `TELEGRAM_API_ID`/`HASH` não autentica de verdade no Telegram; testar qualquer fluxo de Telegram localmente (copier, "Conectar Telegram", `send_test_signal.py`) já exige um valor real no `.env`, independente desta spec.

### 2. `src/telegram_copier.py`
Remove a duplicação — lê direto de `settings`, sem fallback local:
```python
self.api_id = settings.TELEGRAM_API_ID
self.api_hash = settings.TELEGRAM_API_HASH
```

### 3. `docs/sdd/IMPEDIMENTOS.md`
Atualiza o "Onde" do IMP-013 pra incluir `src/core/config.py` (`TELEGRAM_API_ID`/`TELEGRAM_API_HASH`) e `src/telegram_copier.py` (duplicação do mesmo fallback).

### Arquivos tocados
- `src/core/config.py`
- `src/telegram_copier.py`
- `docs/sdd/IMPEDIMENTOS.md`

Sem migração de schema.

## Critérios de aceite

- [ ] `grep -rn "24906269\|4826f9dd0be48b617f94fc04b88ffabc" src/` não encontra mais nenhuma ocorrência.
- [ ] `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` com placeholder e `ENVIRONMENT=production` falha ao subir com erro claro.
- [ ] Mesmo placeholder com `ENVIRONMENT=development` continua subindo normalmente (sem regressão no fluxo de dev local que já usa credenciais reais no `.env`).
- [ ] `src/telegram_copier.py` não redeclara mais os valores — usa `settings.TELEGRAM_API_ID`/`settings.TELEGRAM_API_HASH` diretamente.
- [ ] IMP-013 atualizado com os novos arquivos/campos.
- [ ] Import de todos os módulos tocados limpo; app sobe sem erro **depois** que `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` reais forem definidos no `.env` local.

## Impacto em performance

Nenhum — só validação de configuração no boot, não toca hot path.

## Plano de rollback

`git revert`. Sem migração de schema. Se o ambiente local não tiver `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` configurados a tempo, o rollback imediato é reverter o commit (volta pro fallback antigo) enquanto o `.env` correto é aplicado — mesmo plano já usado na spec-010.

## Aprovação

- [ ] Revisado contra `docs/sdd/CONSTITUICAO.md` (§2 fonte única — remove duplicação do fallback; §3 zona de alto risco; §6 segredos — objetivo central; §7 autorização)
- [ ] Confirmação explícita: `.env` local já tem (ou terá, antes de aplicar) `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` reais definidos — necessário pra não quebrar o boot com `ENVIRONMENT=production`
- [ ] Aprovado explicitamente pelo usuário antes do início da implementação
