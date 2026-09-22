# 014 — Corrige open-status da IQ Option travando 30s por causa de "digital" (não usado)

- **Status:** Em revisão
- **Autor:** josemaramorim (via Claude)
- **Data:** 2026-09-22
- **Impedimento(s) relacionado(s):** IMP-008 ("Staleness de até 120s no status de abertura de ativo", `docs/sdd/IMPEDIMENTOS.md`) — esta spec não resolve o impedimento inteiro (o polling de 120s continua existindo), mas corrige a causa de ele **nunca produzir dado nenhum** hoje.
- **Zona de alto risco?** **Sim** — toca `src/broker/iqoption.py`. Exige autorização explícita antes de qualquer edição de código (Constituição §3), mesmo sendo uma troca localizada dentro de um único método.

## Problema

`_refresh_open_status` (`src/broker/iqoption.py:180-204`) roda a cada 120s em thread de background (`_start_background_refresh`, linha 246) e **sempre falha**, sem exceção, confirmado no log do usuário (repetindo por 35+ minutos seguidos, todo ciclo):
```
ERROR - **warning** get_digital_underlying_list_data late 30 sec
WARNING - Falha ao consultar open-status: 'NoneType' object is not subscriptable
```

Causa raiz exata: `_refresh_open_status` chama `self.api.get_all_open_time()` (linha 188), método da lib vendorizada (`vendor/iqoptionapi/iqoptionapi/stable_api.py:253-289`). Esse método monta o resultado em blocos sequenciais:
1. **`turbo`/`binary`** (linhas 254-268) — via `get_all_init_v2()`, **sempre bem-sucedido** (confirmado: nunca aparece o log `"get_all_init_v2 late 30 sec"`, só o do digital).
2. **`digital`** (linhas 270-280) — chama `get_digital_underlying_list_data()`, que espera até 30s por uma resposta da IQ Option que nunca chega nesta conta, e retorna `None`. A linha seguinte (271) faz `None["underlying"]`, e o `TypeError: 'NoneType' object is not subscriptable` **derruba a função inteira antes de retornar** — descartando os dados de turbo/binary já calculados com sucesso no bloco 1.
3. `other`/`forex`/`crypto` (linhas 283+) — nunca alcançado.

**O bloco "digital" não é usado pelo RDE.** `_build_asset_map` (`src/broker/iqoption.py:123-145`) só indexa ativos das categorias `turbo` e `binary` (linha 133: `for cat in ("turbo", "binary")`) — nenhum código do projeto lê ou precisa de dado "digital". Estamos pagando o custo de uma chamada que sempre falha (30s de espera bloqueante, num loop `while ... : pass` **sem `time.sleep`**, prendendo a thread — e o GIL do Python — por até 30s a cada ciclo) por uma categoria que não afeta nada do fluxo de sinais.

### Impacto real no hot path

`_variation_open` (`iqoption.py:207-217`), chamada por `send_order` (linha 414, caminho real de disparo de ordem), decide se filtra uma variação de ativo fechada. Como `_open_map` nunca é populado, `_variation_open` cai no fallback `if not self._open_map: return True` (linha 209-210) — **fail-open, não bloqueia ordem** (sem risco de rejeição indevida). Mas isso também significa que **o filtro de ativo aberto/fechado está efetivamente desligado**, silenciosamente, o tempo todo — a proteção existe no código mas nunca roda de verdade.

## Contexto

`get_all_init_v2()` (o bloco 1, turbo/binary) já é chamado *internamente* por `get_all_open_time()` de qualquer forma — não é uma chamada de rede nova; é o mesmo primeiro passo que já rodava (e sempre funcionava) antes de travar no passo do digital. Chamar `get_all_init_v2()` diretamente, sem passar pelo restante de `get_all_open_time()`, não adiciona nenhuma chamada de rede que não existisse já — só remove a parte que sempre falhava.

Fora de escopo: não editamos a lib vendorizada (`vendor/iqoptionapi/`) — a mudança fica inteira em `src/broker/iqoption.py`, replicando (só para turbo/binary) a mesma transformação que `get_all_open_time()` já faz nessas duas categorias (linhas 254-268 do vendorizado), usando o mesmo estilo de acesso defensivo (`.get(...)`) já usado em `_build_asset_map` no mesmo arquivo, em vez do acesso direto por índice (`active["name"]`) que a lib vendorizada usa.

## Proposta

### `src/broker/iqoption.py`
`_refresh_open_status` (linhas 180-204) para de chamar `self.api.get_all_open_time()` / `self.api.api.get_all_open_time()`. Passa a chamar `self.api.get_all_init_v2()` diretamente e montar `self._open_map` só com as categorias `turbo`/`binary`, mesma lógica de "aberto" que a lib já usa (`enabled` e `is_suspended`), com acesso defensivo (`.get`) em vez de indexação direta:

```python
def _refresh_open_status(self):
    """Consulta a corretora e monta self._open_map[nome_completo] = aberto_agora.

    So turbo/binary -- unicas categorias usadas por _build_asset_map. Nao usa
    get_all_open_time() da lib vendorizada: esse metodo tambem calcula status
    "digital" (nao usado aqui) e trava ate 30s quando a corretora nao responde
    essa parte, descartando os dados de turbo/binary ja calculados com sucesso
    (spec 014 / IMP-008).
    """
    self._open_map = {}
    if self.api is None:
        return
    try:
        init_data = None
        if hasattr(self.api, "get_all_init_v2"):
            init_data = self.api.get_all_init_v2()
        elif hasattr(self.api, "api") and hasattr(self.api.api, "get_all_init_v2"):
            init_data = self.api.api.get_all_init_v2()

        if not init_data or not isinstance(init_data, dict):
            return
        for category in ("turbo", "binary"):
            actives = (init_data.get(category) or {}).get("actives", {})
            if not isinstance(actives, dict):
                continue
            for _, active in actives.items():
                if not isinstance(active, dict):
                    continue
                raw = active.get("name", "")
                name = raw[raw.index(".") + 1:] if "." in raw else raw
                if not name:
                    continue
                self._open_map[name] = bool(active.get("enabled")) and not bool(active.get("is_suspended"))
        if self._open_map:
            logger.info(f"Open-status atualizado: {sum(1 for v in self._open_map.values() if v)} ativos abertos de {len(self._open_map)}")
    except Exception as e:
        logger.warning(f"Falha ao consultar open-status: {e}")
```

### Arquivos tocados
- `src/broker/iqoption.py` (1 método, `_refresh_open_status`)

Nenhuma mudança em `vendor/iqoptionapi/`, `_variation_open`, `is_asset_open`, `send_order` ou no intervalo de 120s do polling em background — só a fonte do dado.

## Critérios de aceite

- [ ] `trades.log` deixa de registrar `get_digital_underlying_list_data late 30 sec` / `Falha ao consultar open-status: 'NoneType' object is not subscriptable` a cada ciclo.
- [ ] `trades.log` passa a registrar `Open-status atualizado: N ativos abertos de M` a cada ciclo de 120s (evidência de que `_open_map` está sendo populado de verdade pela primeira vez).
- [ ] Ciclo de refresh deixa de levar ~30s (busy-wait) — passa a completar no tempo de uma chamada normal de `get_all_init_v2()` (mesma ordem de grandeza do `Aguardando api_option_init_all` já observado no startup, alguns segundos).
- [ ] `send_order` continua funcionando normalmente para ativos abertos (comportamento observável inalterado quando o ativo está aberto).
- [ ] App sobe sem erro; import do módulo limpo.

## Impacto em performance

**Melhora**: remove um busy-wait bloqueante de até 30s (sem `sleep`, prendendo uma thread OS e contendendo pelo GIL) a cada ciclo de 120s — hoje 100% das vezes, pela observação do log. Não adiciona nenhuma chamada de rede nova (o `get_all_init_v2()` já era o primeiro passo interno do método antigo). Como consequência colateral desejada, o filtro de ativo aberto/fechado em `send_order` (via `_variation_open`) passa a ter dado real pela primeira vez, em vez de sempre cair no fallback fail-open.

## Plano de rollback

`git revert` — mudança de 1 método, sem estado persistido alterado. Se `get_all_init_v2()` também passar a falhar por algum motivo futuro (não observado até agora), o comportamento é o mesmo fail-open de hoje (`_open_map` vazio → `_variation_open` retorna `True`) — sem regressão pior que o estado atual.

## Aprovação

- [ ] Revisado contra `docs/sdd/CONSTITUICAO.md` (§1 performance-first — objetivo central; §3 zona de alto risco — autorização explícita obrigatória; §4 código limpo — acesso defensivo, sem `except Exception: pass` silencioso; §5 sem código morto — não introduz novo; §7 autorização)
- [ ] Aprovado explicitamente pelo usuário antes do início da implementação
