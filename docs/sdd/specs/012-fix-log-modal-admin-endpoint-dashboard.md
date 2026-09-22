# 012 — Corrige HTTP 400 no console de logs do próprio dashboard

- **Status:** Em revisão
- **Autor:** josemaramorim (via Claude)
- **Data:** 2026-09-22
- **Impedimento(s) relacionado(s):** Nenhum registrado em `IMPEDIMENTOS.md` — regressão de integração após a mudança de log global para log por usuário (IMP-001), encontrada nesta sessão a partir de relato do usuário.
- **Zona de alto risco?** **Não** (não toca `src/broker/*`, `telegram_copier.py`, `tradingview_bridge.py`, `executor.py`; toca só `frontend/`). Ainda assim, por mudar comportamento observável em `frontend/`, segue a regra 3 do `CLAUDE.md`: spec + autorização explícita antes do código.

## Problema

No Dashboard do próprio usuário, o botão "Ver Console de Logs" abre `LogTerminalModal` e retorna **HTTP 400**, terminal vazio (`Total: 0 linhas (0 KB) | Exibindo 0`).

Causa: `frontend/app/dashboard/page.tsx:613-618` passa `isAdmin={Boolean(estado?.is_admin)}` ao `LogTerminalModal`. Quando o usuário logado tem `is_admin: true` (caso do screenshot — conta "ADMINISTRADOR"), o modal usa o ramo admin (`LogTerminalModal.tsx:49-51`) e chama `GET /admin/logs/copier?lines=200` — **sem `user_id`**.

O backend (`src/main.py:527-539`, rota `/admin/logs/copier`) exige explicitamente `?user_id=<id>` desde que os logs deixaram de ser um `copier.log` único global e passaram a ser `copier_{user_id}.log` por usuário (IMP-001, comentário na linha 494-496 e 537-538):
```python
if not user_id:
    raise HTTPException(status_code=400, detail="Informe ?user_id=<id> — o log do copier agora é por usuário.")
```
`dashboard/page.tsx` nunca teve motivo pra enviar um `user_id` — o contexto ali é sempre "ver o log do usuário logado", nunca de outro usuário. O backend está correto; o mismatch é só na escolha de endpoint no frontend.

Existe uma rota que já resolve exatamente esse caso sem exigir parâmetro nenhum: `GET /copier/logs` (`src/main.py:563-570`), que usa `user.id` do próprio token autenticado. É a rota que o `isAdmin=false` (default) já chama (`LogTerminalModal.tsx:51`).

## Contexto

`isAdmin` no `LogTerminalModal` hoje mistura dois conceitos diferentes: (1) "este usuário tem a role de admin" e (2) "esta chamada deve usar o endpoint de suporte admin (ver log de QUALQUER usuário por id)". No Dashboard, o contexto é sempre autoconsulta — a role do usuário (ser ou não admin) é irrelevante pra qual log deve ser mostrado; deveria ser sempre o próprio.

**Achado relacionado, fora do escopo desta spec:** o botão global "Ver Logs" em `frontend/app/admin/page.tsx:655-660` (Painel Admin) também passa `isAdmin={true}` sem nenhum `user_id` — ali o 400 também ocorre, mas a causa é diferente: é um botão único no cabeçalho do painel, não vinculado a nenhum usuário selecionado, então não existe um `user_id` óbvio pra mandar. Corrigir esse caso exigiria adicionar uma UI de seleção de usuário (escopo maior, decisão de produto) — não é tratado aqui; fica registrado para o usuário decidir se quer abrir spec separada.

## Proposta

### `frontend/app/dashboard/page.tsx`
Remove o mismatch: o modal de logs do próprio Dashboard passa a sempre usar o ramo não-admin do `LogTerminalModal` (que já chama `GET/DELETE` nada — só `GET /copier/logs`, resolvido via token). Troca:
```tsx
isAdmin={Boolean(estado?.is_admin)}
```
por:
```tsx
isAdmin={false}
```
(ou remove a prop, já que o default do componente é `false`.)

Efeito colateral aceito: o botão "🧹 Limpar" (que só aparece com `isAdmin=true` e hoje chamaria `DELETE /admin/logs/copier` sem `user_id`, quebrando do mesmo jeito) deixa de aparecer no Dashboard próprio. Não há regressão real — essa ação já estava quebrada nesse contexto; não existe hoje uma rota `DELETE /copier/logs` (autoconsulta) para substituí-la, e criar uma está fora do escopo deste fix.

### Arquivos tocados
- `frontend/app/dashboard/page.tsx` (1 linha)

Sem migração de schema, sem mudança de backend.

## Critérios de aceite

- [ ] No Dashboard do próprio usuário (admin ou não), "Ver Console de Logs" carrega o log sem erro HTTP 400.
- [ ] Terminal exibe linhas reais de `copier_{user_id}.log` do usuário logado (ou a mensagem de "nenhum log gerado ainda", se o arquivo não existir) — não mais "Total: 0 linhas | Exibindo 0" por erro.
- [ ] Auto-refresh (3s padrão) continua funcionando sem novos erros 400.
- [ ] Botão "🧹 Limpar" não aparece mais no modal quando aberto a partir do Dashboard próprio (antes quebrava do mesmo jeito; comportamento aceito, não é regressão de algo que funcionava).
- [ ] Painel Admin (`admin/page.tsx`) inalterado — continua com o problema pré-existente do botão global sem `user_id`, fora do escopo desta spec.

## Impacto em performance

Nenhum — só corrige qual endpoint HTTP é chamado no frontend, não adiciona chamada nova.

## Plano de rollback

`git revert` — mudança de 1 linha, sem estado persistido alterado.

## Aprovação

- [ ] Revisado contra `docs/sdd/CONSTITUICAO.md` (§7 autorização)
- [ ] Aprovado explicitamente pelo usuário antes do início da implementação
