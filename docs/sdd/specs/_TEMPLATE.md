# NNN — Título curto da mudança

- **Status:** Rascunho | Em revisão | Aprovada | Implementado
- **Autor:** 
- **Data:** 
- **Impedimento(s) relacionado(s):** IMP-XXX (ver `docs/sdd/IMPEDIMENTOS.md`), ou "Nenhum"
- **Zona de alto risco?** Sim/Não — se sim (toca `src/broker/*`, `telegram_copier.py`, `tradingview_bridge.py`, `executor.py`), exige autorização explícita antes da implementação (ver `docs/sdd/CONSTITUICAO.md` §3)

## Problema

O que está errado ou faltando, hoje, com evidência concreta (arquivo:linha, comportamento observado, log/erro).

## Contexto

Por que isso importa agora. Trade-offs já conhecidos (ex.: decisões anteriores de latência que motivaram o estado atual).

## Proposta

O que muda, em termos de comportamento — não é necessário pseudocódigo detalhado, mas deve ser claro o suficiente para alguém implementar sem ambiguidade. Listar os arquivos que devem ser tocados.

## Critérios de aceite

- [ ] Critério 1 (comportamento verificável)
- [ ] Critério 2
- [ ] ...

## Impacto em performance

Essa mudança adiciona latência, remove latência, ou é neutra? Onde, e por quê. Se adiciona qualquer chamada de rede/DB no hot path, justificar explicitamente (ver Constituição §1).

## Plano de rollback

Como desfazer se algo der errado em produção (reverter commit, flag, migração reversível, etc).

## Aprovação

- [ ] Revisado contra `docs/sdd/CONSTITUICAO.md`
- [ ] Aprovado explicitamente pelo usuário antes do início da implementação
