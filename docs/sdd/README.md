# SDD no RDE_5 — Spec-Driven Development

Este diretório é o processo de trabalho que passamos a seguir para qualquer mudança relevante no RDE_5 a partir de agora. Ele existe porque o histórico do projeto mostra um padrão recorrente: correções reativas em produção (bugs de latência, regras de negócio duplicadas e divergentes, um erro de sintaxe commitado direto na `main`) por falta de um passo de especificação/revisão antes de mexer no código. Ver [`docs/sdd/IMPEDIMENTOS.md`](IMPEDIMENTOS.md) para o inventário atual desses problemas.

Regras de fundo (o "porquê" de cada regra) estão em [`docs/sdd/CONSTITUICAO.md`](CONSTITUICAO.md) — leia antes de propor ou aprovar qualquer spec.

## O fluxo

1. **Toda mudança de comportamento** (bugfix, feature, refactor que muda comportamento observável) nasce como uma spec em `docs/sdd/specs/`, a partir de [`docs/sdd/specs/_TEMPLATE.md`](specs/_TEMPLATE.md). Nome do arquivo: `NNN-slug-curto.md` (numeração sequencial, ex: `001-fix-pid-global.md`).
2. A spec referencia o(s) impedimento(s) relacionado(s) em `IMPEDIMENTOS.md`, se houver.
3. A spec é revisada e **precisa de aprovação explícita do usuário antes de virar código** — nenhuma implementação começa a partir de uma spec ainda não aprovada. Isso vale mesmo para mudanças pequenas em `src/broker/*`, `telegram_copier.py`, `tradingview_bridge.py` e `executor.py` (código de execução de trade), que são tratados como zona de alto risco.
4. Depois de aprovada, a implementação segue os critérios de aceite descritos na spec. Ao terminar, a spec é marcada como `Status: Implementado` e, se ela resolvia um impedimento, o impedimento correspondente é atualizado em `IMPEDIMENTOS.md`.
5. Mudanças puramente de documentação, tooling ou scripts auxiliares (não tocam em `src/` ou `frontend/`) podem dispensar spec, a critério do usuário.

## Por que "spec antes de código" aqui

Numa plataforma de execução de trades, um bug silencioso não é só um bug de código — é dinheiro real (ordem no ativo errado, P&L calculado errado, sessão de um usuário derrubando a de outro). O custo de escrever 10 linhas de spec antes é sempre menor que o custo de descobrir o problema em produção. Ver exemplos concretos em [`IMPEDIMENTOS.md`](IMPEDIMENTOS.md).
