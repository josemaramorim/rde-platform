# 016 — Resolução do canal Telegram: troca match por substring por match exato normalizado

- **Status:** Implementado
- **Autor:** josemaramorim (via Claude)
- **Data:** 2026-09-23
- **Impedimento(s) relacionado(s):** Nenhum registrado ainda em `IMPEDIMENTOS.md` — risco identificado nesta sessão ao planejar o teste manual de sinais (`scripts/README.md`).
- **Zona de alto risco?** **Sim** — toca `src/telegram_copier.py`, decide qual canal do Telegram dispara ordem real pra **todo** usuário em produção. Exige autorização explícita antes de qualquer edição de código (Constituição §3), mesmo sendo uma troca localizada dentro de um único método.

## Problema

`TelegramCopier.start()` (`src/telegram_copier.py:1414-1442`) resolve qual chat monitorar em 3 passos, na ordem:
1. `TELEGRAM_CHAT_ID` (ID numérico exato) — seguro, sem ambiguidade.
2. `TELEGRAM_GROUP_NAME`: match por **substring nos dois sentidos** (`cfg_clean in d_clean or d_clean in cfg_clean`), primeiro diálogo que bater, sem checar se há mais de um candidato.
3. Fallback: se o nome configurado contém `"rde"` ou `"r&de"`, procura **qualquer** grupo/canal da conta que também contenha `"rde"` no nome — primeiro que aparecer em `get_dialogs()`, sem qualquer outra validação.

O passo 3 é o mais arriscado: `"rde"` é uma substring curta e comum. Qualquer grupo/canal do qual a conta conectada seja membro — incluindo um canal de **teste** nomeado "Teste RDE", como o que criamos nesta sessão — bate nesse critério. Se a conta conectada de qualquer usuário (produção ou teste) for membro de mais de um grupo com "rde" no nome, o copier escolhe o primeiro da lista **silenciosamente**, sem erro, sem log de alerta — só uma linha informativa (`🎯 [TELEGRAM] Canal ativo e monitorado exclusivamente: ...`) que ninguém costuma observar em tempo real. Resultado possível: o copier de um usuário de produção grudar no canal errado, processando (ou deixando de processar) sinais de um canal diferente do pretendido.

## Contexto

O comentário original ("Fallback inteligente apenas se o nome configurado for variações de R&DE") sugere que o objetivo era tolerar diferença de formatação entre o nome configurado no servidor e o nome real do grupo no Telegram (emoji, `&`, espaçamento, maiúsculas) — não abrir mão de qualquer correspondência. Dá pra manter exatamente essa tolerância sem o risco de match por substring: normalizando os dois nomes (remover tudo que não for letra/número, minúsculo) e exigindo **igualdade exata** depois da normalização, em vez de "um contém o outro" ou "ambos contêm uma palavra-chave fixa".

Isso também resolve o passo 2 (substring nos dois sentidos tem o mesmo problema em menor escala — dois canais onde o nome de um é substring do outro colidem do mesmo jeito).

**Efeito colateral esperado, relevante para o teste manual em andamento:** com o fix, "Teste RDE" deixa de bater com o `TELEGRAM_GROUP_NAME` de produção (que hoje contém "rde" solto) — a normalização de "Teste RDE" vira `testerde`, diferente de `rde` (de "R&DE🇧🇷" normalizado). Isso é o comportamento **correto** (evita justamente a ambiguidade que motivou esta spec), mas significa que testar localmente vai exigir `TELEGRAM_CHAT_ID` (ID do canal de teste) ou `TELEGRAM_GROUP_NAME=Teste RDE` no `.env` do ambiente de teste, em vez de depender do fallback antigo "combinar por conter rde".

## Proposta

### `src/telegram_copier.py`
Dentro de `start()`, troca os passos 2 e 3 (linhas 1424-1440) por uma única resolução por nome, exata após normalização:

```python
def _normalize_group_name(name: str) -> str:
    """Mantem so letras/numeros (case-insensitive) -- tolera emoji/espaco/pontuacao
    dos dois lados, sem virar match por substring solto (spec 016)."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())

...
# 2. Nome configurado: match EXATO apos normalizar. Se mais de um grupo bater,
#    e ambiguo -- recusa a adivinhar e erra de forma visivel.
if not monitored_names and group_name_cfg:
    cfg_norm = _normalize_group_name(group_name_cfg)
    candidates = [
        d for d in dialogs
        if (d.is_channel or d.is_group) and _normalize_group_name(d.name) == cfg_norm
    ]
    if len(candidates) == 1:
        d = candidates[0]
        self.target_chats = [d.id]
        monitored_names.append(f"'{d.name}' (ID: {d.id})")
    elif len(candidates) > 1:
        names = ", ".join(f"'{d.name}' (ID: {d.id})" for d in candidates)
        err_msg = (
            f"Nome de canal '{group_name_cfg}' é ambíguo -- {len(candidates)} grupos "
            f"da conta batem após normalização: {names}. Configure TELEGRAM_CHAT_ID "
            f"com o ID exato em vez de depender do nome."
        )
        logger.error(f"❌ [TELEGRAM] {err_msg}")
        self.update_live_status(f"Erro: {err_msg}")
        self.is_running = False
        return
```

O passo 3 antigo (fallback "contém rde") é **removido** — a normalização exata já cobre o caso de uso original (tolerar formatação) sem o risco de substring solta.

O bloqueio de segurança existente (linhas 1444-1451, "canal não encontrado") continua igual — cobre o caso de zero candidatos.

### Arquivos tocados
- `src/telegram_copier.py` (1 método, `start()`)

Sem migração de schema, sem mudança de config (`.env`) exigida — quem já usa `TELEGRAM_CHAT_ID` ou tem o nome batendo exatamente (após normalização) não percebe diferença.

## Critérios de aceite

- [x] Um `TELEGRAM_GROUP_NAME` com emoji/espaço/caixa diferente do nome real do grupo (ex.: `"R&DE🇧🇷"` configurado vs grupo `"R&DE 🇧🇷 "`) continua resolvendo corretamente — confirmado via teste da função de normalização isolada (`norm('R&DE🇧🇷') == norm('R&DE 🇧🇷 ')` → `True`).
- [x] Uma conta membro de dois grupos cujos nomes só compartilham a substring "rde" (produção vs "Teste RDE") **não** resolve mais para o mesmo — confirmado (`norm('R&DE🇧🇷') == norm('Teste RDE')` → `False`); no código, esse caso agora cai no bloqueio de "canal não encontrado" (zero candidatos) em vez de grudar por engano.
- [x] Caso de zero candidatos continua com a mesma mensagem de erro de hoje ("canal não encontrado") — bloco inalterado.
- [x] `TELEGRAM_CHAT_ID` (passo 1, match por ID exato) continua funcionando sem nenhuma mudança de comportamento — bloco inalterado.
- [x] App/copier sobe sem erro; import do módulo limpo — `python -m py_compile` e `import src.telegram_copier` OK.

## Impacto em performance

Nenhum — troca de lógica de comparação de string dentro de uma resolução que já rodava uma vez no `start()` do copier (não é hot path de execução de ordem).

## Plano de rollback

`git revert` — sem estado persistido alterado. Se o fix causar falso-negativo em algum ambiente com nome de grupo muito diferente do configurado (caso não prevemos), o efeito é o copier recusar iniciar com erro claro (fail-safe), não executar no canal errado — reversível a qualquer momento revertendo o commit.

## Aprovação

- [x] Revisado contra `docs/sdd/CONSTITUICAO.md` (§1 performance-first — neutro; §3 zona de alto risco — autorização explícita obrigatória; §4 código limpo — sem `except: pass` silencioso, erro de ambiguidade logado com contexto; §7 autorização)
- [x] Aprovado explicitamente pelo usuário antes do início da implementação (2026-09-23)
