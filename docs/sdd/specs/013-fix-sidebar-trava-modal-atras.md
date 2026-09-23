# 013 — Corrige Sidebar aparecendo por cima de modais em tela cheia

- **Status:** Implementado
- **Autor:** josemaramorim (via Claude)
- **Data:** 2026-09-22
- **Impedimento(s) relacionado(s):** Nenhum registrado em `IMPEDIMENTOS.md` — bug visual encontrado nesta sessão a partir de relato do usuário (screenshot do modal de logs com a Sidebar sobreposta/misturada).
- **Zona de alto risco?** **Não** (não toca `src/broker/*`, `telegram_copier.py`, `tradingview_bridge.py`, `executor.py`; toca só `frontend/`, 1 arquivo compartilhado por todas as páginas). Segue a regra 3 do `CLAUDE.md`: spec + autorização explícita antes do código.

## Problema

Qualquer modal em tela cheia (`fixed inset-0 ... z-50`) — hoje existem dois: `LogTerminalModal.tsx` (usado em `dashboard/page.tsx` e `admin/page.tsx`) e o modal de notas do cliente em `admin/page.tsx` — renderiza com a Sidebar visível **por cima** da metade esquerda, em vez de o backdrop escuro cobrir a tela inteira (visível no screenshot do usuário: menu "Dashboard/Planilha/Estatísticas/..." aparece sobreposto ao terminal de logs).

Causa: `frontend/app/layout.tsx:30-38` estrutura o layout raiz assim:
```tsx
<div className="flex min-h-screen w-full relative">
  {!isLoginPage && <Sidebar />}                         {/* Sidebar.tsx:46 -> z-50 */}
  <main className="... relative z-10">{children}</main> {/* z-10 */}
</div>
```
`<Sidebar>` (`components/Sidebar.tsx:46`, `position: sticky` + `z-50`) e `<main>` (`position: relative` + `z-10`) são **irmãos diretos** no mesmo container. Como `position + z-index != auto` cria um novo contexto de empilhamento (stacking context) em cada um, a comparação de qual fica por cima acontece **nesse nível raiz**: `Sidebar` (z-50) > `main` (z-10) — então **toda a subárvore de `main` fica sempre atrás da Sidebar**, não importa qual `z-index` um elemento `fixed` *dentro* de `main` declare (o `z-50` do modal só é comparado com outros elementos dentro do próprio contexto de `main`; nunca "escapa" pra competir com a Sidebar, que está fora desse contexto). É por isso que um modal com `z-50` dentro de `main` (`z-10`) perde pra Sidebar (`z-50`) mesmo tendo o mesmo número de z-index nominal.

## Contexto

A Sidebar (`components/Sidebar.tsx`) não tem nenhum comportamento de overlay/drawer mobile (sem `position: fixed`, sem estado aberto/fechado, sem transform) — é sempre uma coluna fixa de `w-64` dentro do `flex` do layout, lado a lado com `main`, nunca sobrepondo conteúdo normal por conta própria. O `z-50` nela não tem função observável hoje (nada depende dela estar acima de outra coisa em uso normal, sem modal aberto) — é o `z-10` de `main`, mais baixo, que faz a Sidebar "vencer" indevidamente qualquer modal renderizado dentro de `main`.

## Proposta

### `frontend/components/Sidebar.tsx`
Remove o `z-50` do `<aside>` (linha 46) — a Sidebar deixa de forçar um contexto de empilhamento mais alto que `main`. Sem `z-index` explícito, ela participa do empilhamento padrão (ordem do DOM), e `main` (que já tem `z-10`, maior que `auto`) passa a poder ficar por cima quando necessário — incluindo qualquer modal `fixed`/`z-50` renderizado dentro dela.

### Arquivos tocados
- `frontend/components/Sidebar.tsx` (1 linha — remove uma classe CSS)

Nenhuma mudança em `app/layout.tsx`, `LogTerminalModal.tsx` ou no modal de notas do admin — o fix é só na Sidebar, e corrige os dois modais existentes de uma vez (raiz do problema é compartilhada), sem precisar tocar em cada modal individualmente.

## Critérios de aceite

- [x] Com o modal "Terminal de Logs ao Vivo" aberto (Dashboard), a Sidebar não aparece mais visível/sobreposta — confirmado pelo usuário via screenshot: modal cobrindo a tela inteira, nenhum item de menu visível nas bordas (diferente do screenshot original do bug).
- [ ] Mesmo teste com o modal de "Notas do Admin" (`admin/page.tsx`) — não testado explicitamente nesta sessão, mas usa o mesmo mecanismo (`fixed inset-0 z-50` dentro de `main`), correção compartilhada.
- [x] Fora de qualquer modal aberto, a Sidebar continua normal — sem relato de regressão visual no uso comum.
- [x] Nenhuma outra sobreposição indevida percebida (`ToastContainer`/`VersionCheck` fora de `main`, não afetados por esta mudança).

## Impacto em performance

Nenhum — mudança puramente de CSS/stacking, sem lógica nova.

## Plano de rollback

`git revert` — mudança de 1 linha.

## Aprovação

- [x] Revisado contra `docs/sdd/CONSTITUICAO.md` (§7 autorização)
- [x] Aprovado explicitamente pelo usuário antes do início da implementação (2026-09-22)
