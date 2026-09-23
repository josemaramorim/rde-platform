# Como usar — `send_test_signal.py`

Testa o fluxo Telegram → ordem → resultado sem esperar um sinal real chegar. O script só **envia** a mensagem de teste; o `telegram_copier.py` da aplicação precisa já estar rodando e escutando o canal antes de você mandar o sinal.

> Pra configuração de ambiente (canal de teste, credenciais, restart do backend) e troubleshooting, ver [`docs/GUIA_TESTE_MANUAL_SINAL_TELEGRAM.md`](../docs/GUIA_TESTE_MANUAL_SINAL_TELEGRAM.md) — este README aqui cobre só o script em si.

## Passo a passo

1. **Canal de teste no Telegram** + **conta de teste separada** (membro só desse canal) + **usuário RDE de teste** com a corretora em modo **demo**, com essa conta de teste conectada a ele (fluxo normal de "Conectar Telegram" no dashboard). Ligue o copier desse usuário e confirme que ele achou o canal de teste.
2. Definir as credenciais da conta de teste (uma vez por sessão de terminal):
   ```bash
   export TG_TEST_API_ID="..."
   export TG_TEST_API_HASH="..."
   export TG_TEST_PHONE="+55..."
   ```
3. Disparar o sinal:
   ```bash
   python scripts/send_test_signal.py --channel "SEU-CANAL-TESTE" \
       --direction CALL --symbol EURUSD-OTC --timeframe M1
   ```
4. Acompanhar `copier_{user_id}.log`, o dashboard/`live_status_{user_id}.json`, `live_operations_{user_id}.json`, e o extrato da conta demo na corretora.

## Variações

- `--entry-in 60` — adiciona horário de entrada (testa a espera até o fechamento da vela) em vez de disparar na hora.
- `--pre-alert` — envia como pré-alerta (deve ser ignorado pelo copier).
- `--raw "..."` — mensagem crua, formato livre.
- `--dry-run` — só mostra a mensagem, não envia (não precisa das credenciais `TG_TEST_*`).
