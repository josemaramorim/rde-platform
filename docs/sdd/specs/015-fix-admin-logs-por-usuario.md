# 015 — Painel Admin: "Ver Logs" passa a ser por usuário (corrige HTTP 400)

- **Status:** Implementado
- **Autor:** josemaramorim (via Claude)
- **Data:** 2026-09-23
- **Impedimento(s) relacionado(s):** Nenhum registrado em `IMPEDIMENTOS.md` — mesma raiz da spec 012 (IMP-001, log por usuário), parte que ficou explicitamente fora de escopo naquela spec.
- **Zona de alto risco?** **Não** (não toca `src/broker/*`, `telegram_copier.py`, `tradingview_bridge.py`, `executor.py`; toca só `frontend/`). Segue a regra 3 do `CLAUDE.md`: spec + autorização explícita antes do código.

## Problema

O botão **"🖥️ Logs do Servidor"** no cabeçalho do Painel Admin (`frontend/app/admin/page.tsx:302-305`) abre `LogTerminalModal` com `isAdmin={true}` (linha 659) e **nenhum `userId`** — o componente não tem sequer essa prop hoje. O modal chama `GET /admin/logs/copier?lines=200`, que exige `?user_id=<id>` desde a mudança pra log por usuário (`src/main.py:536-538`, IMP-001) — 400 garantido, confirmado pelo usuário via screenshot (mesmo sintoma da spec 012, mas essa parte foi explicitamente deixada de fora dali).

Causa de fundo: o rótulo do botão ("Logs do Servidor") é um resquício de quando existia um único `copier.log` global — não existe mais "log do servidor" como conceito, só `copier_{user_id}.log` por usuário. Um botão de cabeçalho, sem usuário nenhum selecionado, não tem como saber qual `user_id` mandar.

## Contexto

A tabela de usuários do Painel Admin já tem um padrão de ação por linha (`admin/page.tsx:543-554`): botões "Revogar/Liberar" e "Gerir" (que abre o modal de notas/plano via `setModal(u)`, usando o `User` daquela linha). O jeito natural de corrigir é o mesmo: trocar o botão global por uma ação por linha ("Logs"), que já sabe de qual usuário está falando.

## Proposta

### 1. `frontend/components/LogTerminalModal.tsx`
- Nova prop opcional `userId?: string | null`.
- `fetchLogs`: quando `isAdmin` e `userId` presente, acrescenta `&user_id=${encodeURIComponent(userId)}` na URL de `/admin/logs/copier`. Quando `isAdmin` e `userId` **ausente**, não chama a API — mostra direto a mensagem "Selecione um usuário para ver os logs." (evita repetir o 400 por design, em vez de só tratar o erro depois que ele acontece).
- `handleClearServerLogs`: mesmo tratamento — acrescenta `&user_id=` na chamada `DELETE /admin/logs/copier` quando aplicável.
- Sem mudança no ramo não-admin (`isAdmin=false`, usado pelo Dashboard) — `userId` é ignorado nesse caso, continua usando `/copier/logs` (token resolve o usuário).

### 2. `frontend/app/admin/page.tsx`
- Novo estado `const [logsUser, setLogsUser] = useState<User | null>(null);`.
- Botão de cabeçalho "🖥️ Logs do Servidor" (linhas 302-305) é **removido** (não faz mais sentido sem um usuário associado).
- Nova ação por linha na tabela (ao lado de "Gerir", linha ~549-552): botão "Logs" que faz `setLogsUser(u); setShowLogsModal(true);`.
- `<LogTerminalModal>` (linha ~655-660) passa a receber `userId={logsUser?.id ?? null}`; `onClose` também limpa `setLogsUser(null)`.

### Arquivos tocados
- `frontend/components/LogTerminalModal.tsx`
- `frontend/app/admin/page.tsx`

Nenhuma mudança de backend — `src/main.py:527-539` já está correto, só exige o parâmetro que o frontend não mandava.

## Critérios de aceite

- [x] Painel Admin não tem mais botão de "Logs" global no cabeçalho.
- [x] Cada linha da tabela de usuários tem uma ação "🖥️ Logs" que abre o terminal já com o `user_id` daquela linha, via `&user_id=` na query string.
- [x] `LogTerminalModal` não chama a API quando `isAdmin` e sem `userId` — mostra "Selecione um usuário para ver os logs." em vez de repetir o 400.
- [x] Botão "🧹 Limpar" só aparece quando `isAdmin && userId`; a chamada `DELETE` inclui `?user_id=`.
- [x] Dashboard próprio (`dashboard/page.tsx`, spec 012) inalterado — continua usando `/copier/logs` sem `userId` (prop opcional, default `null`, ignorada no ramo não-admin).
- [x] `npx tsc --noEmit` limpo após as mudanças.

## Impacto em performance

Nenhum — mudança de UI/parâmetro de request, sem novo hot path.

## Plano de rollback

`git revert` — sem estado persistido alterado.

## Aprovação

- [x] Revisado contra `docs/sdd/CONSTITUICAO.md` (§7 autorização)
- [x] Aprovado explicitamente pelo usuário antes do início da implementação (2026-09-23)
