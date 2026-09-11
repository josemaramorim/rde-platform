# `iqoptionapi` — dependência vendorizada

Este pacote foi congelado dentro do repositório em vez de instalado via `pip install git+...` diretamente do GitHub. Ver `docs/sdd/specs/005-vendorizar-iqoptionapi.md` para o motivo (reprodutibilidade — a instalação anterior não tinha pin de commit).

## Proveniência

- **Repositório de origem:** https://github.com/Lu-Yi-Hsun/iqoptionapi
- **Commit vendorizado:** `7dd95a81c079e8af7a3728aa2aa194154f29ba3f`
- **Data da vendorização:** 2026-09-11
- **Motivo do commit escolhido:** é exatamente o commit que já estava instalado em produção/dev antes desta mudança (confirmado via `pip show iqoptionapi` → `direct_url.json`) — zero mudança de comportamento, só a origem da instalação muda. No momento da vendorização, esse commit também era o `HEAD` do repositório de origem (`git ls-remote`), ou seja, não havia atualização mais recente sendo deixada de fora.

## Licença

O repositório de origem **não inclui um arquivo de licença** (`LICENSE`/`LICENSE.md`/etc. ausentes no commit vendorizado, verificado antes de copiar). Isso já era verdade da instalação via pip — a vendorização não piora nem melhora a situação de licenciamento, só a documenta explicitamente aqui.

## O que foi vendorizado

Apenas o necessário para instalar e importar o pacote:
- `iqoptionapi/` — código-fonte do pacote (65 arquivos `.py`, ~311KB)
- `setup.py` — usado pela instalação local editável (`pip install -e ./vendor/iqoptionapi`)
- `requirements.txt` — dependências declaradas pela própria lib (`pylint`, `requests`, `websocket-client==0.56` — pin antigo, herdado da lib, não introduzido por esta vendorização)
- `README_UPSTREAM.md` — README original do projeto (renomeado para não conflitar com este arquivo)

Deliberadamente **não** vendorizado (redundante para uso como dependência): `.git/`, `.github/`, `tests/`, `docs/`, `image/`, arquivos de CI/cobertura (`.travis.yml`, `.coverage`, `coverage.xml`), e documentação solta do repo original (`old_document.md`, `ACTIVE_CODE.txt`, `instrument.txt`, `mkdocs.yml`, `pylint.rc`).

## Patches locais

Nenhum até o momento — código idêntico ao commit de origem.

## Como atualizar

Não há processo automático. Para atualizar pra um commit mais novo: repetir o processo acima (clonar o repo de origem no commit desejado, revisar o diff, copiar por cima desta pasta, atualizar este arquivo com o novo commit/data), testar manualmente contra uma conta de teste antes de mergear.
