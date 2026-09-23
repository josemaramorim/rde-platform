# 019 — Cálculo de lucro por diferença de saldo "vaza" entre ordens consecutivas

- **Status:** Implementado
- **Autor:** josemaramorim (via Claude)
- **Data:** 2026-09-23
- **Impedimento(s) relacionado(s):** Nenhum registrado ainda — bug real observado no teste manual desta sessão (dois WINs reais na corretora viraram 1 LOSS + 1 WIN com lucro absurdo no app).
- **Zona de alto risco?** **Sim** — toca `src/telegram_copier.py`, lógica de P&L (lucro/prejuízo) usada pra decidir meta diária, stop loss e o que é mostrado como resultado real ao usuário. Exige autorização explícita antes de qualquer edição de código (Constituição §3).

## Problema

Teste manual em 2026-09-23 (canal "Teste RDE"), duas ordens consecutivas em `EURTHB-OTC`, stake $115.07 cada:

- **16:08:42** — ordem enviada. Às 16:09:45-49, `get_contract_status` retornou "incerto" duas vezes seguidas. O código caiu no fallback (`src/telegram_copier.py:1101-1107`): compara saldo atual com saldo de antes da ordem — não subiu, marca **LOSS** (`-$115.07`).
- **16:10:12** — nova ordem enviada. Dessa vez `get_contract_status` confirmou **WIN** direto, sem fallback. Lucro calculado como `saldo_atual - saldo_antes_desta_ordem` (linha 1112): **+$622,29** — muito acima do payout esperado (tipicamente 70-95% do stake, ou seja, ~$80-110 num stake de $115).

O extrato da própria corretora (conferido pelo usuário) mostra **as duas ordens como WIN**, não uma LOSS e uma WIN. Ou seja: a primeira ordem foi classificada errada, e o lucro da segunda "engoliu" o crédito atrasado da primeira.

**Causa raiz:** quando `get_contract_status` fica incerto, a corretora provavelmente ainda não tinha *assentado* (creditado) o resultado no saldo — por isso o saldo não parecia ter subido no momento do cheque (linha 1099), e a ordem foi julgada LOSS por engano. O crédito real chegou **depois**, durante a janela de espera da ordem seguinte. Como `_balance_before_trade` da segunda ordem foi capturado usando esse saldo desatualizado (`self.current_balance`, ainda sem o crédito atrasado da primeira), o `current_balance - _balance_before_trade` da segunda ordem incluiu **os dois créditos somados**.

## Contexto

O comentário em `telegram_copier.py:1109-1110` já documenta que o cálculo por diferença de saldo foi escolhido no lugar de um percentual fixo de payout (IMP-005) — não vamos reverter essa decisão. O problema aqui é mais específico: o fallback de status incerto desiste rápido demais (1 retry, 2s) e não há nenhuma proteção contra o resultado do cálculo ser um valor claramente impossível pra um payout de opção binária/turbo (que nunca chega a 100%, então um lucro maior que o próprio stake já é suspeito).

## Proposta

### `src/telegram_copier.py` — dentro do handler de resultado da ordem (linhas ~1091-1125)

1. **Mais tempo/tentativas antes de desistir e cair no fallback de saldo:** troca 1 retry de 2s por até 3 retries de 3s (até ~9s a mais de espera pro resultado assentar antes de confiar na diferença de saldo).
2. **Sanity check no lucro calculado de um WIN:** se o `profit` calculado for maior que `stake * 2` (folga generosa acima de qualquer payout real de opção binária/turbo, que não passa de ~100%), loga um aviso claro e limita o valor registrado a `stake * 0.95` (um payout razoável) em vez de propagar um número que sabidamente inclui crédito de outra ordem — protege a meta diária e o stop loss de serem corrompidos por um valor impossível.

```python
trade_status = self.broker.get_contract_status(contract_id)
retries = 0
while trade_status == "error" and retries < 3:
    logger.warning(f"Status da ordem {contract_id} incerto. Aguardando saldo assentar (tentativa {retries+1}/3)...")
    await asyncio.sleep(3)
    trade_status = self.broker.get_contract_status(contract_id)
    retries += 1

self.current_balance = self.broker.get_balance()

if trade_status == "error":
    logger.warning(f"Status da ordem {contract_id} permaneceu incerto apos {retries} tentativas. Usando variacao de saldo como arbitro.")
    if self.current_balance > self._balance_before_trade:
        trade_status = "won"
    else:
        trade_status = "lost"

if trade_status == "won":
    profit = self.current_balance - self._balance_before_trade
    if profit <= 0:
        await asyncio.sleep(3)
        self.current_balance = self.broker.get_balance()
        profit = self.current_balance - self._balance_before_trade
    if profit <= 0:
        logger.warning(f"WIN confirmado mas saldo nao refletiu ganho (delta={profit:.2f}). Registrando profit=0.")
        profit = 0.0
    elif profit > stake * 2:
        logger.warning(
            f"Profit calculado (${profit:.2f}) muito acima do payout esperado para "
            f"stake ${stake:.2f} -- provavel credito atrasado de ordem anterior "
            f"somado ao desta (spec 019). Limitando a ${stake*0.95:.2f}."
        )
        profit = round(stake * 0.95, 2)
    self.success_count += 1
else:
    profit = -stake
```

Isso reduz a frequência do problema (menos vezes cai no fallback frágil) e evita que, quando acontecer mesmo assim, um número absurdo se propague pra meta/stop loss/histórico do usuário. Não elimina 100% o risco de má-classificação pontual de uma ordem isolada (isso exigiria uma API de resultado por contrato mais confiável da corretora, fora do escopo aqui) — mas impede o efeito cascata observado no teste.

### Arquivos tocados
- `src/telegram_copier.py` (1 trecho do método de execução de ordem)

Sem migração de schema.

## Critérios de aceite

- [x] Uma ordem cujo `get_contract_status` fica incerto agora tenta até 3x (9s extras) antes de cair no fallback de saldo, reduzindo a chance de julgar errado por saldo ainda não assentado.
- [x] Um `profit` calculado maior que `2x` o stake é limitado a `95%` do stake e loga aviso — validado isoladamente: `$622,29` (caso real do teste manual) vira `$109,32`; um payout normal de `$94,36` (82% de `$115,07`) passa sem alteração.
- [x] Caminho feliz (status confirmado rápido, profit dentro do esperado) inalterado.
- [x] Import do módulo limpo (`python -m py_compile` + `import src.telegram_copier`); comportamento observável de LOSS inalterado (`profit = -stake` continua igual).

## Impacto em performance

Pode adicionar até ~9s de espera extra **só no caso raro de status incerto** (não no caminho normal) — aceitável, já que é isso ou registrar um resultado financeiro errado. Não afeta o hot path de disparo de ordem (isso já aconteceu; essa lógica roda só na apuração do resultado, depois da vela fechar).

## Plano de rollback

`git revert` — sem estado persistido alterado (a mudança é só na lógica de cálculo, não em schema).

## Aprovação

- [x] Revisado contra `docs/sdd/CONSTITUICAO.md` (§3 zona de alto risco — autorização explícita obrigatória; §4 código limpo — aviso logado com contexto, não `except: pass`; §7 autorização)
- [x] Aprovado explicitamente pelo usuário antes do início da implementação (2026-09-23)
