# RDE_5

Plataforma de execução de trades em corretoras (IQ Option, Deriv, Quotex, Pocket Option) a partir de sinais (Telegram/TradingView). Requisito não-funcional #1: **latência de disparo de ordem**. Segundo: código limpo e sem regra de negócio duplicada.

## Antes de qualquer mudança

1. Leia **[docs/sdd/CONSTITUICAO.md](docs/sdd/CONSTITUICAO.md)** — regras não-negociáveis do projeto. Não repita o conteúdo dela aqui; abra o arquivo quando for tocar em código.
2. Verifique **[docs/sdd/IMPEDIMENTOS.md](docs/sdd/IMPEDIMENTOS.md)** — problemas conhecidos (ex.: já existe um IMP-XXX para o que você ia mexer?).
3. Toda mudança de comportamento em `src/` ou `frontend/` nasce como uma spec em `docs/sdd/specs/` (template em `docs/sdd/specs/_TEMPLATE.md`) e **precisa de autorização explícita do usuário antes de virar código** — mesmo mudanças pequenas. Ver o fluxo completo em [docs/sdd/README.md](docs/sdd/README.md).
4. **Zona de alto risco** (exige spec + autorização mesmo para 1 linha): `src/broker/*`, `src/telegram_copier.py`, `src/routes/tradingview_bridge.py`, `src/executor.py`.
5. **Toda mudança — código ou docs/processo — vai numa branch própria**, nunca commit direto em `main`/`develop` (Constituição §8). Criar a branch a partir da `main` atualizada antes de implementar.

Não abra os três arquivos de `docs/sdd/` inteiros só por rotina — abra o que for relevante para a tarefa. Isso é intencional para não gastar contexto/tokens à toa.

## Mapa rápido do repo

- `src/main.py` — app FastAPI (rotas, auth, admin) — arquivo grande, cuidado ao editar (ver IMP-010).
- `src/broker/` — adapters por corretora (`iqoption.py`, `deriv.py`, `quotex.py`, `pocketoption.py`) atrás de `base.py`. `connection_manager.py` é código morto (IMP-011), não reconectar.
- `src/telegram_copier.py` — copier do Telegram, roda como subprocesso por usuário.
- `src/routes/tradingview_bridge.py` — webhook do TradingView, processo compartilhado entre usuários (cuidado com bloqueio de event loop aqui).
- `src/routes/admin_routes.py` — API de admin em uso (v2). Endpoints de admin dentro de `main.py` são legado/duplicado — não copiar o padrão deles.
- `src/app/` — scaffold morto, nunca importado. Não editar nem usar como referência.
- `docs/sdd/` — processo de trabalho (constituição, impedimentos, specs). Ver acima.

## Convenções

- Python: type hints em código novo/editado; nunca `except Exception: pass` silencioso — logar o que falhou.
- Nenhum segredo com fallback hardcoded em arquivo versionado (`.env*` fica de fora do git; ver `.gitignore`).
- Sem testes automatizados/CI de verdade ainda (IMP-006) — valide manualmente e descreva como testou.
